import os
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

assert OPENAI_API_KEY, "OPENAI_API_KEY niet gezet"
assert PINECONE_API_KEY, "PINECONE_API_KEY niet gezet"

INDEX_NAME = "knowledge-base"
EMBED_DIM = 1536
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"

client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)

if INDEX_NAME not in pc.list_indexes().names():
    pc.create_index(
        name=INDEX_NAME,
        dimension=EMBED_DIM,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-west-2"),
    )

index = pc.Index(INDEX_NAME)
