import ollama
import time

# "gemma3:1b" is the 1B parameter version of Google's Gemma 3
model_name = "gemma3:1b"

print(f"Checking for {model_name}... (this will auto-download if missing)")

# 1. Pull the model
ollama.pull(model_name)

# 2. Define your prompt
prompt = "what did Mickey Mantle do on June 21, 1960?"

print(f"\nGenerating response for: '{prompt}'...\n")

# 3. Run the model with benchmarking
start_time = time.time()

response = ollama.chat(model=model_name, messages=[
  {
    'role': 'user',
    'content': prompt,
  },
])

end_time = time.time()
total_time = end_time - start_time

# 4. Print the result
print("-" * 50)
print(response['message']['content'])
print("-" * 50)

# 5. Print Benchmarks
# Ollama provides token counts in the response details, allowing accurate TPS calculation
if 'eval_count' in response:
    token_count = response['eval_count']
    tps = token_count / total_time
    print(f"Time taken: {total_time:.2f} seconds")
    print(f"Tokens generated: {token_count}")
    print(f"Speed: {tps:.2f} tokens/sec")
else:
    # Fallback if metadata isn't returned
    print(f"Time taken: {total_time:.2f} seconds")