#################################################################################################
##                                                                                             ##
##                                 NE PAS TOUCHER CETTE PARTIE                                 ##
##                                                                                             ##
## 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 ##
import boto3
from botocore.config import Config
import os
import uuid
from dotenv import load_dotenv
from typing import Union, Optional
import logging
logging.basicConfig(level=logging.DEBUG)
from fastapi import FastAPI, Request, status, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from fastapi import HTTPException

from getSignedUrl import getSignedUrl

load_dotenv()

app = FastAPI()
logger = logging.getLogger("uvicorn")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request,
                                       exc: RequestValidationError):
    exc_str = f'{exc}'.replace('\n', ' ').replace('   ', ' ')
    logger.error(f"{request}: {exc_str}")
    content = {'status_code': 10422, 'message': exc_str, 'data': None}
    return JSONResponse(content=content,
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


class Post(BaseModel):
    title: str
    body: str


my_config = Config(
    region_name='us-east-1',
    signature_version='v4',
)

dynamodb = boto3.resource('dynamodb', config=my_config)
table = dynamodb.Table(os.getenv("DYNAMO_TABLE"))
s3_client = boto3.client('s3',
                         config=boto3.session.Config(signature_version='s3v4'))
bucket = os.getenv("BUCKET")

## ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ##
##                                                                                                ##
####################################################################################################


@app.post("/posts")
async def post_a_post(post: Post, authorization: Optional[str] = Header(default=None)):
    """
    Poste un post ! Les informations du poste sont dans post.title, post.body et le user dans authorization
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is missing")

    # Génération de l'identifiant du post
    post_id = str(uuid.uuid4())
    # Construction de l'item avec clés uniformes
    item = {
        "user": f"USER#{authorization}",
        "post_id": post_id,
        "title": post.title,
        "body": post.body,
        "image": None,
        "labels": []
    }

    try:
        table.put_item(Item=item)
        return JSONResponse(status_code=200, content={
            "status_code": 200,
            "message": "Post created",
            "data": {
                "user": authorization,
                "id": post_id,
                "title": post.title,
                "body": post.body,
                "image": None,
                "labels": []
            }
        })
    except Exception as e:
        logger.error(f"Erreur lors de l'ajout du post: {e}", exc_info=True)
        # Pour debug, renvoyer l'erreur aussi en réponse (à retirer en prod)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/posts")
async def get_all_posts(user: Union[str, None] = None):
    try:
        if user:
            pk = f"USER#{user}"
            resp = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("user").eq(pk))
            items = resp.get("Items", [])
        else:
            resp = table.scan()
            items = resp.get("Items", [])

        posts = []
        for it in items:
            # Vérification que 'user' est bien présent et bien formaté
            raw_user = it.get("user", "")
            if "#" not in raw_user:
                logger.warning(f"User field mal formé dans un post: {raw_user}")
                uid = raw_user  # fallback pour ne pas planter
            else:
                uid = raw_user.split("#", 1)[1]

            pid = it.get("post_id", "")

            image_url = None
            image_key = it.get("image")
            if image_key:
                try:
                    image_url = s3_client.generate_presigned_url(
                        ClientMethod="get_object",
                        Params={"Bucket": bucket, "Key": image_key},
                        ExpiresIn=3600
                    )
                except Exception as e:
                    logger.error(f"Erreur lors de la génération du signed URL: {e}")
                    image_url = None

            posts.append({
                "user": uid,
                "id": pid,
                "title": it.get("title", ""),
                "body": it.get("body", ""),
                "image": image_url,
                "labels": it.get("labels", [])
            })

        return JSONResponse(status_code=200, content={
            "status_code": 200,
            "message": "Posts retrieved",
            "data": posts
        })

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des posts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur serveur lors de la récupération des posts")



@app.delete("/posts/{post_id}")
async def delete_post(post_id: str, authorization: Optional[str] = Header(default=None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is missing")

    pk = f"USER#{authorization}"
    # sk n'est plus une clé composite
    sk = post_id
    try:
        # Récupérer l'item pour avoir la clé S3
        resp = table.get_item(Key={"user": pk, "post_id": sk})
        item = resp.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="Post not found")

        image_key = item.get("image")
        if image_key:
            try:
                s3_client.delete_object(Bucket=bucket, Key=image_key)
            except Exception as e:
                logger.error(f"Suppression S3 échouée: {e}")

        table.delete_item(Key={"user": pk, "post_id": sk})
        return JSONResponse(status_code=200, content={
            "status_code": 200,
            "message": "Post deleted",
            "data": None
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du post: {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur lors de la suppression du post")


#################################################################################################
##                                                                                             ##
##                                 NE PAS TOUCHER CETTE PARTIE                                 ##
##                                                                                             ##
## 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 👇 ##
@app.get("/signedUrlPut")
async def get_signed_url_put(filename: str, filetype: str, postId: str, authorization: Optional[str] = Header(default=None)):
    return getSignedUrl(filename, filetype, postId, authorization)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="debug")

## ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ☝️ ##
##                                                                                                ##
####################################################################################################
