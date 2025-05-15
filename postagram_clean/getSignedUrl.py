##################################################
##                                              ##
##           NE PAS TOUCHER !!!!!!!!!           ## 
##                                              ##
##################################################


import logging
import boto3
from boto3.dynamodb.conditions import Key
import os
import json
import uuid
from pathlib import Path
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

bucket = os.getenv("BUCKET")
print("bucket_name =", bucket)  # DEBUG
s3_client = boto3.client('s3', config=boto3.session.Config(signature_version='s3v4'))
logger = logging.getLogger("uvicorn")

def getSignedUrl(filename: str,filetype: str, postId: str, user):

    filename = f'{uuid.uuid4()}{Path(filename).name}'
    object_name = f"{user}/{postId}/{filename}"

    try:
        url = s3_client.generate_presigned_url(
            Params={
            "Bucket": bucket,
            "Key": object_name,
            "ContentType": filetype
        },
            ClientMethod='put_object'
        )
    except ClientError as e:
        logging.error(e)


    logger.info(f'Url: {url}')
    return {
            "uploadURL": url,
            "objectName" : object_name
        }