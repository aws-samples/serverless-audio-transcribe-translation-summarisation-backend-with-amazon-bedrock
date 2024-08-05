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
dynamodb_client = boto3.resource('dynamodb')
table = dynamodb_client.Table(DYNAMO_TABLE)

def lambda_handler(event, context):
    print(event)

    dynamodb_key = event['requestContext']['authorizer']['claims']['email']

    #get json of objects from dynamodb using dynamodb_key
    dynamodb_response = table.scan(
        FilterExpression=Attr("file_owner").eq(dynamodb_key)
    )
    print(dynamodb_response)

    #check dynamodb_response for errors
    #and exit if found
    if 'Items' not in dynamodb_response:
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
        return_items = dynamodb_response['Items']
        return_items.sort(key=lambda x: x['file_timestamp'], reverse=True)

        return {
            'statusCode': 200,
            'body': json.dumps(return_items),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }