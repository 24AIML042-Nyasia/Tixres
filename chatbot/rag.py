import os
import json
from pathlib import Path
from typing import List, Dict, Any

from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
import faiss

class RAGManager:
    def __init__(self, index_path: str = "chatbot/faiss_index"):
        self.index_path = Path(index_path)
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        if self.index_path.exists():
            self.vectorstore = FAISS.load_local(
                str(self.index_path), 
                self.embeddings, 
                allow_dangerous_deserialization=True
            )
        else:
            # Initialize empty FAISS index
            index = faiss.IndexFlatL2(len(self.embeddings.embed_query("hello")))
            self.vectorstore = FAISS(
                embedding_function=self.embeddings,
                index=index,
                docstore=InMemoryDocstore({}),
                index_to_docstore_id={},
            )

    def add_documents(self, docs_data: List[Dict[str, Any]]):
        documents = []
        for item in docs_data:
            content = item.get("content", "")
            metadata = item.get("metadata", {})
            if content:
                documents.append(Document(page_content=content, metadata=metadata))
        
        if documents:
            self.vectorstore.add_documents(documents)
            self.save()

    def search(self, query: str, k: int = 4) -> List[Document]:
        return self.vectorstore.similarity_search(query, k=k)

    def save(self):
        self.vectorstore.save_local(str(self.index_path))

    def get_context(self, query: str) -> str:
        docs = self.search(query)
        return "\n\n".join([doc.page_content for doc in docs])
