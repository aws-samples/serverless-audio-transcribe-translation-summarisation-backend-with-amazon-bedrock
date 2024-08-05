import json
import boto3
import os
from boto3.dynamodb.conditions import And, Attr

DYNAMO_TABLE = os.environ.get('DYNAMODB_TABLE_NAME')
S3_BUCKET = os.environ.get('APPLICATION_BUCKET')
SOURCE_PREFIX = os.environ.get('SOURCE_PREFIX')
NOTES_PREFIX = os.environ.get('NOTES_PREFIX')
COMPILED_PREFIX = os.environ.get('COMPILED_PREFIX')

s3_client = boto3.client('s3')
dynamodb_client = boto3.client('dynamodb')

def lambda_handler(event, context):
    print(event)

    search_key = event['queryStringParameters']['file']
    dynamodb_key = event['requestContext']['authorizer']['claims']['email']

    dynamodb_response = dynamodb_client.get_item(TableName=DYNAMO_TABLE, Key={'file_name':{'S':str(search_key)}})

    #check dynamodb_response for errors
    #and exit if found
    if 'Item' not in dynamodb_response:
        print("No item found in dynamodb")
        return {
            'statusCode': 200,
            'body': json.dumps("No item found in dynamodb"),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
    else:
        print("Item found in dynamodb")

        return {
            'statusCode': 200,
            'body': json.dumps(dynamodb_response['Item']),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }