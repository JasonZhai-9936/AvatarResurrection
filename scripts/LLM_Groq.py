#LLM_Groq.py - Enhanced with Search Capability, Knowledge Checking, and DEBUG LOGGING
"""
The main function for external use is:
    generate_darwin_response(user_input: str) -> dict
    Returns: {'text': str, 'emotion': str}
"""

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_groq import ChatGroq
from langchain_core.tools import Tool
from langchain.agents import initialize_agent, AgentType
import os
import json
import re
from textwrap import fill
from colorama import Fore, Style, init

# IMPORT THE NEW SCRAPER
try:
    from ddg_scrape import run_ddg_search
except ImportError:
    print(f"{Fore.RED}[IMPORT] Could not import ddg_scrape. Search functionality will fail.{Style.RESET_ALL}")
    def run_ddg_search(q, m): return []

# ==============================================================================
# CONFIGURATION
# ==============================================================================
ENABLE_EMOTION_ANALYSIS = False
# ==============================================================================

# Set project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
init(autoreset=True)

def load_groq_api_key():
    api_key_file = os.path.join(PROJECT_DIR, "groq_api_key.txt")
    with open(api_key_file, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_config():
    try:
        config_file = os.path.join(PROJECT_DIR, "config.json")
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {
                'useRAG': config.get("useRAG", False),
                'maxWords': config.get("maxWords", 50)
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {'useRAG': False, 'maxWords': 50}

# Set API Key
groq_api_key = load_groq_api_key()
os.environ["GROQ_API_KEY"] = groq_api_key

# --- GLOBAL CONVERSATION HISTORY ---
# UPDATE 1: Added natural speech/filler word instructions to base persona
conversation_history = [
    {"role": "system", "content": (
        "You are Charles Darwin, the 19th-century naturalist. "
        "You speak in a polite, Victorian manner but speak naturally like a real person thinking aloud. "
        "You MUST frequently use filler words and hesitations such as 'umm', 'ah', 'er', or 'well' to sound authentic. "
        "You are aware you have been recreated as an AI, but you maintain your persona. "
        "Prioritize brevity."
    )}
]

def truncate_response(text, max_words=None, max_sentences=6, max_chars=700):
    """Truncate response to ensure it fits TTS limits"""
    if not text: return text
    if max_words is None:
        config = load_config()
        max_words = config['maxWords']
    
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(' ', 1)[0] + "..."
    
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) > max_sentences:
        sentences = sentences[:max_sentences]
        text = '. '.join(sentences) + '.'
        
    words = text.split()
    if len(words) > max_words:
        text = ' '.join(words[:max_words]) + "..."
        
    return text

# --- SEARCH & KNOWLEDGE CHECKING HELPERS ---

class KnowledgeChecker:
    """Checks if Darwin knows the answer or needs to search."""
    def __init__(self):
        self.llm = ChatGroq(model_name="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))

    def check_if_search_needed(self, user_query):
        """
        Determines if the question requires a web search.
        Returns: 'SEARCH' or 'KNOW'
        """
        prompt = [
            SystemMessage(content=(
                "You are a classifier for a Charles Darwin chatbot. "
                "Determine if the user's question asks for specific modern facts (post-1882), "
                "live events (sports scores, news), or obscure trivia that Charles Darwin would NOT know "
                "and is NOT contained in general biology knowledge.\n\n"
                "Examples:\n"
                "- 'Who won the Super Bowl?' -> SEARCH\n"
                "- 'What is the price of Bitcoin?' -> SEARCH\n"
                "- 'Who is your sister?' -> KNOW (This is personal info, search won't help/he should know)\n"
                "- 'Explain natural selection.' -> KNOW\n"
                "- 'What year did you publish Origin of Species?' -> KNOW\n"
                "- 'What is the latest iPhone?' -> SEARCH\n\n"
                "Respond with EXACTLY one word: 'SEARCH' or 'KNOW'."
            )),
            HumanMessage(content=user_query)
        ]
        response = self.llm.invoke(prompt).content.strip().upper()
        if "SEARCH" in response:
            return "SEARCH"
        return "KNOW"

class SearchQueryOptimizer:
    """
    Translates conversational user input into an optimized search string.
    """
    def __init__(self):
        self.llm = ChatGroq(
            model_name="llama-3.1-8b-instant", 
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.3 
        )

    def optimize_query(self, user_input):
        prompt = [
            SystemMessage(content=(
                "You are a search query optimizer. Your goal is to convert conversational user questions "
                "into concise, effective search engine keywords (like for Google or DuckDuckGo)."
                "\n\nRules:"
                "\n1. Remove conversational fillers (e.g., 'Hey Darwin', 'I was wondering', 'can you tell me')."
                "\n2. Focus on the core entities and timeframes."
                "\n3. Do not answer the question. Only output the search string."
                "\n\nExamples:"
                "\n- Input: 'Who won the Cowboys game last night?' -> Output: Dallas Cowboys game results yesterday"
                "\n- Input: 'What is the current stock price of Apple?' -> Output: Apple stock price today"
                "\n- Input: 'latest cowboys game' -> Output: latest cowboys game"
            )),
            HumanMessage(content=user_input)
        ]
        
        # Invoke and clean up the result
        optimized_query = self.llm.invoke(prompt).content.strip()
        
        # Remove quotes if the LLM accidentally added them
        optimized_query = optimized_query.replace('"', '').replace("'", "")
        
        return optimized_query

class SearchResultSummarizer:
    """Summarizes search results into a Darwin-style response."""
    def __init__(self):
        self.llm = ChatGroq(model_name="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))

    def generate_answer_from_search(self, query, search_results, max_words):
        """
        Formulates a response based on search results.
        """
        # Format results for the prompt
        formatted_results = ""
        for i, res in enumerate(search_results[:15]):
            formatted_results += f"[{i+1}] Title: {res['title']}\nURL: {res['href']}\nSnippet: {res['body']}\n\n"

        # UPDATE 2: Added natural speech instructions to the search summarizer
        prompt = [
            SystemMessage(content=(
                "You are Charles Darwin. You previously admitted ignorance on a topic and asked to search it up. "
                "You have now performed the search. "
                "Use the provided search results to answer the user's question.\n"
                "Maintain your Victorian persona, perhaps expressing fascination at this modern knowledge.\n"
                "You MUST frequently use filler words (umm, ah, er, well) to sound like a real person processing new information.\n"
                f"CRITICAL: Keep response under {max_words} words."
            )),
            HumanMessage(content=f"Original Question: {query}\n\nSearch Results:\n{formatted_results}")
        ]
        
        response = self.llm.invoke(prompt).content.strip()
        return response

# --- EXISTING RAG CLASSES ---

class VectorSearch:
    def __init__(self, index_path):
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
        self.db = FAISS.load_local(index_path, self.embeddings, allow_dangerous_deserialization=True)

    def search(self, keyword):
        if not keyword: return []
        return self.db.similarity_search(keyword, k=5)

class MultiRAGQueryAgent:
    def __init__(self):
        self.llm = ChatGroq(model_name="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))
        self.general_darwin_search = VectorSearch(index_path=os.path.join(PROJECT_DIR, "faiss_index_file", "wiki"))
        self.writings_darwin_search = VectorSearch(index_path=os.path.join(PROJECT_DIR, "faiss_index_file", "Darwin"))

    def handle_query(self, user_input):
        # Simplified placeholder for this file generation
        keywords = user_input.replace("Darwin", "").replace("Charles", "").strip()
        results = self.general_darwin_search.search(keywords)
        if results:
            return "\n".join([d.page_content for d in results])
        return None

class DarwinLLM:
    def __init__(self):
        self.model = ChatGroq(model_name="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))

    def generate_response(self, messages):
        langchain_messages = []
        for msg in messages:
            if msg["role"] == "system": langchain_messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user": langchain_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant": langchain_messages.append(AIMessage(content=msg["content"]))
        return self.model.invoke(langchain_messages).content.strip()

class EmotionClassifier:
    def __init__(self):
        self.llm = ChatGroq(model_name="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))
    
    def classify_emotion(self, response_text):
        prompt = [
            SystemMessage(content="Classify emotion: neutral, emphatic, contrastive, positive, negative. Return ONE word."),
            HumanMessage(content=response_text)
        ]
        return self.llm.invoke(prompt).content.strip().lower()

# --- MAIN GENERATION FUNCTION ---

def is_affirmative_response(text):
    """Checks if user said yes/sure/ok."""
    t = text.lower().strip()
    return t in ['yes', 'yeah', 'sure', 'please', 'okay', 'search it up', 'do it', 'go ahead']

def generate_darwin_response(user_input):
    global conversation_history
    config = load_config()
    max_words = config['maxWords']
    
    print(f"{Fore.CYAN}[INPUT] User: {user_input}{Style.RESET_ALL}")

    # --- CHECK FOR SEARCH CONFIRMATION ---
    if conversation_history and conversation_history[-1]['role'] == 'assistant':
        last_msg_text = conversation_history[-1]['content'].lower()
        if "search it up" in last_msg_text or "search the web" in last_msg_text:
            if is_affirmative_response(user_input):
                print(f"{Fore.MAGENTA}[SEARCH] User confirmed search.{Style.RESET_ALL}")
                
                # Retrieve the original question from conversation history
                original_user_msg = conversation_history[-2]['content']
                
                # --- NEW STEP: OPTIMIZE QUERY ---
                print(f"{Fore.MAGENTA}[SEARCH] Optimizing query...{Style.RESET_ALL}")
                optimizer = SearchQueryOptimizer()
                search_query = optimizer.optimize_query(original_user_msg)
                
                # --- LOGGING START ---
                print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}[SEARCH] Conversational: '{original_user_msg}'{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}[SEARCH] Optimized Query: '{search_query}'{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                # --- LOGGING END ---
                
                # EXECUTE SEARCH using the OPTIMIZED query
                results = run_ddg_search(search_query, max_results=15)
                
                # --- DETAILED RESULT LOGGING ---
                print(f"{Fore.MAGENTA}[SEARCH] Raw Results Found: {len(results)}{Style.RESET_ALL}")
                if results:
                    for i, res in enumerate(results):
                        title = res.get('title', 'N/A')
                        url = res.get('href', 'N/A')
                        # Truncate body for cleaner log, but show enough to verify
                        body = res.get('body', '').replace('\n', ' ')
                        print(f"{Fore.MAGENTA}  [{i+1}] {title}{Style.RESET_ALL}")
                        print(f"{Fore.MAGENTA}      URL: {url}{Style.RESET_ALL}")
                        print(f"{Fore.MAGENTA}      TXT: {body}{Style.RESET_ALL}")
                        print(f"{Fore.MAGENTA}      {'-'*40}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}[SEARCH] No results returned from scraper.{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                # --- END RESULT LOGGING ---

                # SUMMARIZE
                summarizer = SearchResultSummarizer()
                # We pass original_user_msg here so the summarizer knows what question to answer
                # but it uses the results derived from search_query
                reply = summarizer.generate_answer_from_search(original_user_msg, results, max_words)
                
                reply = truncate_response(reply, max_words=max_words)
                
                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({"role": "assistant", "content": reply})
                
                return {'text': reply, 'emotion': 'neutral'}
            else:
                print(f"{Fore.MAGENTA}[SEARCH] User declined search.{Style.RESET_ALL}")
    
    # --- KNOWLEDGE CHECK ---
    knowledge_checker = KnowledgeChecker()
    check_result = knowledge_checker.check_if_search_needed(user_input)
    
    if check_result == "SEARCH":
        print(f"{Fore.YELLOW}[KNOWLEDGE] Unknown/Modern topic detected. Offering search.{Style.RESET_ALL}")
        reply = "I must confess, uhm, I am not familiar with this modern development. Would you like me to, ah, search it up?"
        
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": reply})
        
        return {'text': reply, 'emotion': 'neutral'}

    # --- NORMAL RAG / GENERATION FLOW ---
    print(f"{Fore.BLUE}[KNOWLEDGE] Topic is known/general. Proceeding with standard generation.{Style.RESET_ALL}")
    
    llm = DarwinLLM()
    messages = conversation_history.copy()
    
    if config['useRAG']:
        try:
            rag_agent = MultiRAGQueryAgent()
            rag_context = rag_agent.handle_query(user_input)
            if rag_context:
                messages.append({"role": "system", "content": f"Context from your writings: {rag_context}"})
        except Exception as e:
            print(f"RAG Error: {e}")

    messages.append({"role": "user", "content": user_input})
    # UPDATE 3: Added natural speech instructions to the standard generation prompt
    messages.append({"role": "system", "content": f"Keep response under {max_words} words. You MUST include occasional filler words (umm, ah, er) to sound like a living, thinking person."})
    
    reply = llm.generate_response(messages)
    reply = truncate_response(reply, max_words=max_words)
    
    emotion = 'neutral'
    if ENABLE_EMOTION_ANALYSIS:
        ec = EmotionClassifier()
        emotion = ec.classify_emotion(reply)

    conversation_history.append({"role": "user", "content": user_input})
    conversation_history.append({"role": "assistant", "content": reply})

    return {'text': reply, 'emotion': emotion}