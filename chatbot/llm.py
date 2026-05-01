from langchain_huggingface import HuggingFacePipeline
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch

class LLMManager:
    def __init__(self, model_id: str = "Qwen/Qwen2.5-0.5B-Instruct"):
        self.model_id = model_id
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        
        # Use CPU if no GPU available
        device = 0 if torch.cuda.is_available() else -1
        
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype="auto",
            device_map="auto" if torch.cuda.is_available() else None
        )
        
        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=self.tokenizer,
            max_new_tokens=512,
            temperature=0.7,
            top_p=0.9,
            device=device,
            return_full_text=False # Do not include the prompt in the output
        )
        
        self.llm = HuggingFacePipeline(pipeline=pipe)

    def generate_response(self, prompt: str) -> str:
        response = self.llm.invoke(prompt)
        # Ensure we only return the part after "Answer:" if it somehow got included
        if "Answer:" in response:
            return response.split("Answer:")[-1].strip()
        return response.strip()

    def get_rag_prompt(self, context: str, question: str) -> str:
        return f"""You are a helpful assistant for the Tixres monitoring platform.
Use the following pieces of retrieved context to answer the question. 
If you don't know the answer, just say that you don't know. 

Context:
{context}

Question: {question}

Answer:"""
