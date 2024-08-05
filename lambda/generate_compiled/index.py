import json
import boto3
import os

from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document
from langchain_aws import ChatBedrock
from langchain.chains.summarize import load_summarize_chain
from langchain_text_splitters import RecursiveCharacterTextSplitter

S3_BUCKET = os.environ.get('APPLICATION_BUCKET')
SOURCE_PREFIX = os.environ.get('SOURCE_PREFIX')
NOTES_PREFIX = os.environ.get('NOTES_PREFIX')
COMPILED_PREFIX = os.environ.get('COMPILED_PREFIX')
TRANSLATIONS_PREFIX = os.environ.get('TRANSLATIONS_PREFIX')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID')
SES_SENDER_FROM = os.environ.get('SES_SENDER_FROM')
DYNAMO_TABLE = os.environ.get('DYNAMODB_TABLE_NAME')
send_email = os.environ.get('SES_SEND_EMAIL')

s3_client = boto3.client('s3')
translate_client = boto3.client('translate')
ses_client = boto3.client('ses')
comprehend_client = boto3.client('comprehend')
dynamodb_client = boto3.client('dynamodb')
dynamodb_resource = boto3.resource('dynamodb')

dynamo_table = dynamodb_resource.Table(DYNAMO_TABLE)

#add Bedrock runtime
bedrock_runtime = boto3.client(service_name="bedrock-runtime")

model_kwargs = {
    "max_tokens": 512,
    "temperature": 0
}
#create Bedrock client
claude_3_client = ChatBedrock(
    client=bedrock_runtime,
    model_id=BEDROCK_MODEL_ID,
    model_kwargs=model_kwargs,
)

def lambda_handler(event, context):
    print(event)

    # Load transcript
    transcript_key = event['Records'][0]['s3']['object']['key']
    tokens = transcript_key.split('/')[1].split('.')

    transcript_name = tokens[0]
    file_format = tokens[1]
    source_uri = 's3://{}/{}'.format(S3_BUCKET, transcript_key)
    output_key = '{}/{}.txt'.format(NOTES_PREFIX, transcript_name)

    s3_client.download_file(Bucket=S3_BUCKET, Key=transcript_key, Filename='/tmp/transcript.txt')
    with open('/tmp/transcript.txt') as f:
        contents = json.load(f)

    # Get transcript from JSON
    transcript = contents['results']['transcripts'][0]['transcript']
    transcript_language = contents['results']['language_code']
    transcript_language_first2 = transcript_language[:2]

    #make a file of the transcript (by speaker), summary, and notes
    speaker = ""
    transcript_by_speaker = []
    
    compiled_file = ["Original Transcript","",transcript,"","",""]
    
    #append the transcript by speaker
    compiled_file.append("Full Transcript - Grouped by Speaker")
    compiled_file.append("")
    count_speaker = 0
    
    print("Start speaker loop")
    for part in contents['results']['items']:
        #very first iteration - make some defaults
        if(count_speaker == 0):
            speaker = part['speaker_label']
        
        if(speaker != part['speaker_label']):
            #change of speaker - need to add the sentence to a list, and then empty it
            compiled_file.append(speaker+" - "+' '.join(transcript_by_speaker))
            transcript_by_speaker = []
            speaker = part['speaker_label']
        
        transcript_by_speaker.append(part['alternatives'][0]['content'])
        
        #increment the count
        count_speaker+=1
    #if finished the loop - need to also add whats left to list
    compiled_file.append(speaker+" - "+' '.join(transcript_by_speaker))
    
    print("Finished speaker loop")
    
    
    #start summarisation // chunk file.
    # Invoke endpoint with transcript and instructions
    results = {}

    try:
        # Summarize transcript
        text_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", ".", " "], chunk_size=1000, chunk_overlap=350 
        )
        splits = text_splitter.split_text(transcript)
        docs = [Document(page_content=t) for t in splits]
        
        map_prompt_template = "{text}\n\nWrite a few sentences in English summarizing the above:"
        map_prompt = PromptTemplate(template=map_prompt_template, input_variables=["text"])
        
        combine_prompt_template = "{text}\n\nWrite a detailed analysis, in English of the above with a maximum 200 words:"
        combine_prompt = PromptTemplate(template=combine_prompt_template, input_variables=["text"])

        return_intermediate_steps = False
        chain  = load_summarize_chain(llm=claude_3_client, chain_type="map_reduce", map_prompt=map_prompt, combine_prompt=combine_prompt, return_intermediate_steps=return_intermediate_steps)

        if return_intermediate_steps:
            results = chain.invoke({"input_documents": docs}, return_only_outputs=True)
        else:
            results = chain.invoke(docs, return_only_outputs=True)

        print(results)

        compiled_file.append("")
        compiled_file.append("")
        compiled_file.append("Summarisation Results")
        compiled_file.append("")
        compiled_file.append("Summary")
        compiled_file.append(results['output_text'])
        compiled_file.append("")
        compiled_file.append("Summary Chunks")
        if(return_intermediate_steps):
            for step in results["intermediate_steps"]:
                compiled_file.append(step)

    except Exception as e:
        print('Error generating text')
        print(e)
        raise

    # Save response to S3
    with open('/tmp/output.txt', 'w') as f:
        json.dump(results, f)

    s3_client.put_object(Bucket=S3_BUCKET, Key='{}/{}.txt'.format(NOTES_PREFIX, transcript_name), Body=open('/tmp/output.txt', 'rb'))
    
    print("attempting translate if not English")
    if(transcript_language_first2 != "en"):
        print("language code from: "+transcript_language_first2)
        #translate the transcript from english to french and store it
        translate_response = translate_client.translate_text(Text=transcript,
                                        SourceLanguageCode=transcript_language_first2,
                                        TargetLanguageCode="en")
        
        #add translation to compiled output
        compiled_file.append("")
        compiled_file.append("")
        compiled_file.append("Translation Results")
        compiled_file.append(translate_response['TranslatedText'])
        
        with open('/tmp/translation_output.txt', 'w') as f:
            json.dump(translate_response, f)
        #upload file to s3
        s3_client.put_object(Bucket=S3_BUCKET, Key='{}/{}.txt'.format(TRANSLATIONS_PREFIX, transcript_name), Body=open('/tmp/translation_output.txt', 'rb'))

    print("Translate complete")
    
    #send compiled file to S3    
    print("start compiled file")
    with open('/tmp/compiled.txt', mode='w', encoding='utf-8') as compiled_tmp_file:
        compiled_tmp_file.write('\n'.join(compiled_file))
    s3_client.put_object(Bucket=S3_BUCKET, Key='{}/{}.txt'.format(COMPILED_PREFIX, transcript_name), Body=open('/tmp/compiled.txt', 'rb'))
    print("end compiled file")
    
    message = '\n'.join(compiled_file)
    
    # to do: get email address from DynamoDB from key (filename split by _)
    print("get dynamodb user")
    search_key = transcript_name.split("_")
    print("Search key: "+search_key[0])
    
    response = dynamodb_client.get_item(TableName=DYNAMO_TABLE, Key={'file_name':{'S':str(search_key[0])}})
    print(response)

    #add the message to the DynamoDB item
    update_response = dynamo_table.update_item(
        Key={'file_name': str(search_key[0]) },
        UpdateExpression="set combined_summary=:r",
        ExpressionAttributeValues={
            ':r': str(message) },
        ReturnValues="UPDATED_NEW")
    
    print("Update item")
    print(update_response)
    print("end dynamodb")

    if(send_email == "true"):
        email_sender = SES_SENDER_FROM
        email_recipient = response['Item']['file_owner']['S']

        email_response = ses_client.send_email(
            Source=email_sender,
            Destination={
                'ToAddresses': [
                    email_recipient,
                ],
            },
            Message={
                'Subject': {
                    'Data': 'Transcribe: Your file has been trancribed and summarised'
                },
                'Body': {
                    'Text': {
                        'Data': message,
                    }
                }
            }
        )
        print(email_response)

    # Return response
    return {
        'statusCode': 200,
        'body': {
            'message': json.dumps('Completed summary job {}'.format(transcript_name)),
            'results': results
        }
    }
