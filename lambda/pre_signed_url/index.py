import os
import json
import logging
import boto3
import uuid
import datetime

from botocore.exceptions import ClientError
from botocore.client import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.client('dynamodb')
ses = boto3.client('ses', region_name='eu-west-1')

def lambda_handler(event, context):

    print(event)

    #generate random S3 filename - this will prevent users uploading the same filename more than once
    filename_uuid = str(uuid.uuid4())

    #get S3 bucket from environment variable
    bucket = os.environ.get('APPLICATION_BUCKET')
    prefix = os.environ.get('SOURCE_PREFIX')
    dynamo_table = os.environ.get('DYNAMODB_TABLE_NAME')
    send_email = os.environ.get('SES_SEND_EMAIL')
    
    transcript_key = event['queryStringParameters']['file']
    tokens = transcript_key.split('.')

    authenticated_user = event['requestContext']['authorizer']['claims']['cognito:username']
    authenticated_email = event['requestContext']['authorizer']['claims']['email']

    transcript_name = tokens[0]
    file_format = tokens[1]

    allowed_files = {"mp3","m4a"}
    if file_format in allowed_files:
        print("Exists")
        key = prefix+"/"+filename_uuid+"."+file_format

        current_time = datetime.datetime.now()
        time_stamp = current_time.timestamp()

        file_timestamp = str(int(time_stamp))

        dynamodb.put_item(TableName=dynamo_table, Item={'file_name':{'S':filename_uuid},'file_owner':{'S':authenticated_email},'file_timestamp':{'S': file_timestamp }, 'file_original': {'S': transcript_key} , 'combined_summary': {'S':str("File summary not ready yet - please try again in a few moments.") } } )
    
        if(send_email == "true"):
            email_sender = os.environ.get('SES_SENDER_FROM')
            email_recipient = authenticated_email

            email_response = ses.send_email(
                Source=email_sender,
                Destination={
                    'ToAddresses': [
                        email_recipient,
                    ],
                },
                Message={
                    'Subject': {
                        'Data': 'Transcribe: Your file has been uploaded'
                    },
                    'Body': {
                        'Text': {
                            'Data': 'Your file has been uploaded and is ready to be processed. File key:'+filename_uuid,
                        }
                    }
                }
            )

        #load S3 client - inc config
        #1 - legacy sig version won't work with simple xhttp requests
        #2 - when first spinning up the environment the domain name isn't resolved so you get a 307 response for the cors request causing the browser to 500 error
        s3_client = boto3.client('s3', config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}))
    
        #try to generate put object pre signed URL
        try:
            #try to generate URL // 2 minute timeline for submission
            response = s3_client.generate_presigned_url('put_object',Params={'Bucket': bucket, 'Key': key }, ExpiresIn=120)
        except ClientError as e:
            return_message = e.response['Error']['Message']
            return_status=500
        else:
            #create object for return message
            return_message = {
                    'key':key,
                    'pre_signed_url': response
                }
            return_status=200
    else:
        print("Does not exist")
        return_status=500
        return_message = "Not allowed file type"

    #return to front end service
    return {
        'statusCode': return_status,
        'body': json.dumps(return_message),
        'headers': {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        },
    }
