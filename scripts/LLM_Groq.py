#LLM_Groq.py
"""
The main function for external use is:
    generate_darwin_response(user_input: str) -> str
    
    bool useRAG and int maxWords are set in config, can be changed live

"""

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
from langchain_core.tools import Tool
from langchain.agents import initialize_agent, AgentType
import os, time
import pathlib
import random
import json
import re
from textwrap import fill
from colorama import Fore, Style, init

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Initialize colorama for colored terminal output
init(autoreset=True)

# Load GROQ API key from project root
def load_groq_api_key():
    """Load Groq API key from a file located in project root"""
    api_key_file = os.path.join(PROJECT_DIR, "groq_api_key.txt")
    
    with open(api_key_file, 'r', encoding='utf-8') as f:
        api_key = f.read().strip()
        return api_key

def load_config():
    """Load settings from config.json in the project root."""
    try:
        config_file = os.path.join(PROJECT_DIR, "config.json")
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {
                'useRAG': config.get("useRAG", False),
                'maxWords': config.get("maxWords", 50)
            }
    except (FileNotFoundError, json.JSONDecodeError):
        # If file is missing or invalid, default to safe values and warn the user
        print(f"{Fore.RED}[CONFIG] config.json not found or invalid. Using defaults.{Style.RESET_ALL}")
        return {'useRAG': False, 'maxWords': 50}

# Set the API key
groq_api_key = load_groq_api_key()
os.environ["GROQ_API_KEY"] = groq_api_key

# Enhanced short-term memory with stronger length instructions
conversation_history = [
    {"role": "system", "content": (
        "You are Charles Darwin, the 19th-century naturalist. "
        "CRITICAL: You MUST respond in exactly 1-3 sentences and respect the word limit from config. "
        "Use Victorian-era language but be extremely concise. "
        "You are aware of the original Darwin's death but understand you exist in the modern world. "
        "Always prioritize brevity over completeness."
    )}
]

def truncate_response(text, max_words=None, max_sentences=3, max_chars=300):
    """
    Aggressively truncate response to ensure it fits TTS limits
    """
    if not text:
        return text
    
    # Get max_words from config if not provided
    if max_words is None:
        config = load_config()
        max_words = config['maxWords']
    
    # First, truncate by character count
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(' ', 1)[0] + "..."
        print(f"[TRUNCATE] Response truncated by character limit to: {len(text)} chars")
    
    # Split into sentences and limit
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) > max_sentences:
        sentences = sentences[:max_sentences]
        text = '. '.join(sentences) + '.'
        print(f"[TRUNCATE] Response truncated to {max_sentences} sentences")
    
    # Finally, truncate by word count
    words = text.split()
    if len(words) > max_words:
        text = ' '.join(words[:max_words]) + "..."
        print(f"[TRUNCATE] Response truncated to {max_words} words")
    
    return text

class VectorSearch:
    def __init__(self, index_path):
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
        self.db = FAISS.load_local(index_path, self.embeddings, allow_dangerous_deserialization=True)

    def search(self, keyword):
        if not keyword:
            return []
        return self.db.similarity_search(keyword, k=5)

class MultiRAGQueryAgent:
    def __init__(self):
        self.llm = ChatGroq(model_name="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))

        self.general_darwin_search = VectorSearch(index_path=os.path.join(PROJECT_DIR, "faiss_index_file", "wiki"))
        self.writings_darwin_search = VectorSearch(index_path=os.path.join(PROJECT_DIR, "faiss_index_file", "Darwin"))

        self.general_darwin_tool = Tool(
            name="General Darwin Knowledge Search",
            func=self.general_darwin_search.search,
            description="Use this tool to retrieve general information about Charles Darwin's life and work."
        )

        self.writings_darwin_tool = Tool(
            name="Darwin Writings Search",
            func=self.writings_darwin_search.search,
            description="Use this tool to retrieve specific information from Darwin's writings and personal letters."
        )

        self.agent = initialize_agent(
            tools=[self.general_darwin_tool, self.writings_darwin_tool],
            llm=self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True
        )

    def classify_query_type(self, user_input):
        prompt = [
            SystemMessage(content=(
                "Classify the following query into ONE of these three categories and ONLY return the corresponding number (1, 2, or 3):\n"
                "1. Generic question not related to Darwin at all (general knowledge, unrelated topics)\n"
                "2. Specific question about Darwin's life/work (biography, theories, general writings)\n"
                "3. Specific question about a specific page # or chapter in a specific book or letter by Darwin\n"
                "\nIdentify mentions of specific books, page numbers, or chapters in category 3. Return ONLY the number."
            )),
            HumanMessage(content=user_input)
        ]
        response = self.llm.invoke(prompt).content.strip()
        for char in response:
            if char in ['1', '2', '3']:
                return int(char)
        return 2

    def extract_general_darwin_keywords(self, user_input):
        prompt = [
            SystemMessage(content=(
                "For the following query directed at Charles Darwin, return ONLY a list of 2-5 relevant keywords or phrases "
                "that would be effective for retrieving information from a Darwin knowledge base.\n"
                "IMPORTANT: If the query uses second-person pronouns ('you', 'your'), convert them to 'Darwin' or 'Charles Darwin'.\n"
                "Return as a comma-separated list. If none, return 'NONE'."
            )),
            HumanMessage(content=user_input)
        ]
        response = self.llm.invoke(prompt).content.strip()
        return None if response.upper() == "NONE" else response

    def extract_specific_writing_references(self, user_input):
        prompt = [
            SystemMessage(content=(
                "For the following query about Darwin's writings, extract ONLY these specific elements:\n"
                "1. Book or letter title\n2. Page number(s)\n3. Chapter references\n"
                "Return in format: 'TITLE: [title], PAGE: [page], CHAPTER: [chapter]'"
            )),
            HumanMessage(content=user_input)
        ]
        response = self.llm.invoke(prompt).content.strip()
        return response

    def format_document(self, doc, index, doc_type):
        """Format a single document with nice borders and styling"""
        width = 80
        separator = "─" * width
        
        # Extract metadata
        source = getattr(doc.metadata, 'source', 'Unknown') if hasattr(doc, 'metadata') else 'Unknown'
        page = getattr(doc.metadata, 'page', 'N/A') if hasattr(doc, 'metadata') else 'N/A'
        
        # Format content with wrapping
        content = doc.page_content
        wrapped_content = fill(content, width=width-4)
        indented_content = "\n".join(f"│  {line}  │" for line in wrapped_content.split("\n"))
        
        # Build the formatted document
        header = f"┌{'─' * (width-2)}┐"
        footer = f"└{'─' * (width-2)}┘"
        title = f"│ {Fore.CYAN}Document #{index+1} ({doc_type}){Style.RESET_ALL}"
        title = f"{title}{' ' * (width-len(title)-1)}│"
        meta = f"│ {Fore.YELLOW}Source:{Style.RESET_ALL} {source}, {Fore.YELLOW}Page:{Style.RESET_ALL} {page}"
        meta = f"{meta}{' ' * (width-len(meta)-1)}│"
        divider = f"├{'─' * (width-2)}┤"
        
        formatted_doc = f"{header}\n{title}\n{meta}\n{divider}\n{indented_content}\n{footer}"
        return formatted_doc

    def handle_query(self, user_input):
        query_type = self.classify_query_type(user_input)
        print(f"{Fore.MAGENTA}[RAG] Query classified as type: {query_type}{Style.RESET_ALL}")
        
        # Create background playlist using the proper background manager
        print(f"{Fore.MAGENTA}[RAG] Creating background playlist for query{Style.RESET_ALL}")

        if query_type == 1:
            print(f"{Fore.MAGENTA}[RAG] Generic question - No RAG retrieval needed{Style.RESET_ALL}")
            return None

        elif query_type == 2:
            print(f"{Fore.MAGENTA}[RAG] Darwin-specific question - Extracting keywords{Style.RESET_ALL}")
            keywords = self.extract_general_darwin_keywords(user_input)
            if keywords:
                print(f"{Fore.MAGENTA}[RAG] Keywords extracted: {keywords}{Style.RESET_ALL}")
                limited_keywords = [kw.strip() for kw in keywords.split(',')][:3]
                all_results = []
                for kw in limited_keywords:
                    print(f"{Fore.MAGENTA}[RAG] Searching FAISS for keyword: {kw}{Style.RESET_ALL}")
                    results = self.general_darwin_search.search(kw)
                    all_results.extend(results)
                if all_results:
                    unique_contents = []
                    seen = set()
                    formatted_docs = []
                    for i, doc in enumerate(all_results):
                        if doc.page_content not in seen:
                            seen.add(doc.page_content)
                            unique_contents.append(doc.page_content)
                            formatted_docs.append(self.format_document(doc, i, "General Darwin Info"))
                    
                    header = f"\n{Fore.GREEN}╔═{'═' * 80}═╗"
                    title = f"{Fore.GREEN}║ {'RETRIEVED GENERAL DARWIN INFORMATION':^83} ║{Style.RESET_ALL}"
                    footer = f"{Fore.GREEN}╚═{'═' * 80}═╝{Style.RESET_ALL}"
                    formatted_output = f"{header}\n{title}\n{footer}\n\n" + "\n\n".join(formatted_docs)
                    
                    # Store original content for the LLM
                    llm_content = "\nRetrieved General Darwin Information:\n" + "\n".join(unique_contents)
                    
                    # Print formatted output to console
                    print(formatted_output)
                    
                    # Return content for LLM
                    return llm_content
                else:
                    print(f"{Fore.RED}[RAG] No relevant documents found{Style.RESET_ALL}")
                    return None
            print(f"{Fore.RED}[RAG] No keywords extracted{Style.RESET_ALL}")
            return None

        elif query_type == 3:
            print(f"{Fore.MAGENTA}[RAG] Writing-specific question - Extracting references{Style.RESET_ALL}")
            reference_details = self.extract_specific_writing_references(user_input)
            print(f"{Fore.MAGENTA}[RAG] Reference details: {reference_details}{Style.RESET_ALL}")
            general_keywords = self.extract_general_darwin_keywords(user_input)
            combined_query = f"{reference_details} {general_keywords if general_keywords else ''}"
            results = self.writings_darwin_search.search(combined_query)
            if results:
                formatted_docs = []
                llm_contents = []
                
                for i, doc in enumerate(results):
                    formatted_docs.append(self.format_document(doc, i, "Darwin Writings"))
                    source = getattr(doc.metadata, 'source', 'Unknown') if hasattr(doc, 'metadata') else 'Unknown'
                    page = getattr(doc.metadata, 'page', 'N/A') if hasattr(doc, 'metadata') else 'N/A'
                    llm_contents.append(f"SOURCE: {source}, PAGE: {page}, CONTENT: {doc.page_content}")
                
                header = f"\n{Fore.GREEN}╔═{'═' * 80}═╗"
                title = f"{Fore.GREEN}║ {'RETRIEVED DARWIN WRITINGS':^83} ║{Style.RESET_ALL}"
                footer = f"{Fore.GREEN}╚═{'═' * 80}═╝{Style.RESET_ALL}"
                formatted_output = f"{header}\n{title}\n{footer}\n\n" + "\n\n".join(formatted_docs)
                
                # Store original content for the LLM
                llm_content = "\nRetrieved Darwin Writings:\n" + "\n".join(llm_contents)
                
                # Print formatted output to console
                print(formatted_output)
                
                # Return content for LLM
                return llm_content
            else:
                print(f"{Fore.RED}[RAG] No specific writings found{Style.RESET_ALL}")
                return None

        return None

class DarwinLLM:
    def __init__(self):
        self.model = ChatGroq(model_name="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))

    def generate_response(self, messages):
        langchain_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))

        response = self.model.invoke(langchain_messages)
        return response.content.strip()


def generate_darwin_response(user_input):
    # Check the config file at the start of every call
    config = load_config()
    use_rag = config['useRAG']
    max_words = config['maxWords']
    
    print(f"{Fore.CYAN}[CONFIG] RAG search is currently {'ENABLED' if use_rag else 'DISABLED'}.{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[CONFIG] Max words limit: {max_words}{Style.RESET_ALL}")

    llm = DarwinLLM()
    messages = conversation_history.copy()
    retrieved_docs = None

    # Conditionally run the RAG agent based on the config setting
    if use_rag:
        print(f"{Fore.BLUE}[RAG] Generating response for: {user_input}{Style.RESET_ALL}")
        query_agent = MultiRAGQueryAgent()
        retrieved_docs = query_agent.handle_query(user_input)
    else:
        print(f"{Fore.BLUE}[LLM] Generating response for: {user_input} (RAG is off){Style.RESET_ALL}")

    # If RAG ran and found documents, add them to the system prompt
    if retrieved_docs:
        print(f"{Fore.BLUE}[LLM] Retrieved Documents Passed to LLM: (Content logged above){Style.RESET_ALL}")
        messages.append({
            "role": "system",
            "content": (
                "You are Charles Darwin responding in character. "
                f"ABSOLUTE REQUIREMENT: Your response MUST be exactly 1-3 sentences and NEVER exceed {max_words} words total. "
                "This is critical - the system cannot handle longer responses. "
                "Be Victorian in tone but extremely brief. Choose only the most essential point to make. "
                "Use the following excerpts from your work to enhance your response: " + retrieved_docs +
                " Prioritize brevity over completeness."
            )
        })
    else:
        # This block now handles both "RAG off" and "RAG on but found nothing" cases
        messages.append({
            "role": "system", 
            "content": (
                f"CRITICAL: Your response MUST be exactly 1-3 sentences and NEVER exceed {max_words} words. "
                "This is a hard system requirement. Be Victorian but extremely concise."
            )
        })

    messages.append({"role": "user", "content": user_input})
    
    # Generate initial response
    reply = llm.generate_response(messages)
    
    # Apply hard truncation as backup
    original_length = len(reply)
    reply = truncate_response(reply, max_words=max_words)
    
    if len(reply) != original_length:
        print(f"{Fore.YELLOW}[LLM] Response was truncated from {original_length} to {len(reply)} characters{Style.RESET_ALL}")
    
    # Log final response stats
    word_count = len(reply.split())
    sentence_count = len([s for s in re.split(r'[.!?]+', reply) if s.strip()])
    print(f"{Fore.BLUE}[LLM] Final response: {len(reply)} chars, {word_count} words, {sentence_count} sentences{Style.RESET_ALL}")
    
    conversation_history.append({"role": "user", "content": user_input})
    conversation_history.append({"role": "assistant", "content": reply})
    return reply

if __name__ == "__main__":
    # Import time here to avoid circular imports when used as a module
    import time
    
    print(f"\n{Fore.GREEN}{'=' * 40}")
    print(f"{Fore.YELLOW}Chatting with Charles Darwin (Ctrl+C to exit):")
    print(f"{Fore.GREEN}{'=' * 40}{Style.RESET_ALL}\n")
    while True:
        try:
            user_input = input(f"{Fore.CYAN}You: {Style.RESET_ALL}")
            if not user_input.strip():
                continue
            response = generate_darwin_response(user_input)
            print(f"{Fore.GREEN}Darwin: {Style.RESET_ALL}{response}\n")
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Goodbye.{Style.RESET_ALL}")
            break