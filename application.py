from flask import Flask, request, jsonify, render_template, Response, redirect, url_for
from openai import OpenAI
import csv
from io import StringIO
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from dotenv import load_dotenv
import boto3

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# In-memory storage for generated content (replace with a database in production)
generated_content = {}

def analyze_csv(data):
    print("Entering analyze_csv function")
    print("Input data:", data)

    prompt = f"""Choose from the below list of longtail keywords, and generate blog titles, when possible make the blog titles contextually relevant to the given month for example in november blogs should be thanksgiving themed {__import__('datetime').datetime.now().strftime('%B %Y')}. Rank and align these titles by how well they support Armarkat's goals as outlined above:
    
    Format the output as a JSON array of objects, each containing:
    {{
        "keyword": "...",
        "title": "...",
        "searchVolume": "...",
        "competition": "...",
        "alignment_with_goals":"...",
        "totalScore": ...
    }}
    
    Rank the list by totalScore in descending order. OUTPUT ONLY EXPLICIT RAW JSON
    \n\n{data}"""
    
    print("Generated prompt:", prompt)

    from context import messages
    messages.append({"role": "user", "content": prompt})

    completion = client.chat.completions.create(
        model="o1-preview-2024-09-12",  # Use an appropriate model
        messages=messages
    )
    response_content = completion.choices[0].message.content
    
    print("Raw API response:", response_content)

    # Clean the response content
    response_content = response_content.strip()
    if response_content.startswith("```json"):
        response_content = response_content[7:]  # Remove ```json
    if response_content.endswith("```"):
        response_content = response_content[:-3]  # Remove ```
    
    print("Cleaned response content:", response_content)

    # Attempt to parse the JSON
    try:
        json_data = json.loads(response_content)
        print("Successfully parsed JSON data")
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON. Error: {str(e)}")
        print("Raw content:", response_content)
        return []  # Return an empty list if parsing fails
    
    #messages.append({"role": "assistant", "content": json.dumps(json_data)})
    return json_data  # Return the parsed JSON data as a Python object

def generate_blog_draft(title):
    print("Entering generate_blog_draft function")
    print("Input title:", title)

    prompt = f"""Generate a draft blog post for the following title: "{title}". 
    The blog post should be informative, engaging, and aligned with Armarkat's goals. 
    Include an introduction, main body with key points, and a conclusion."""

    print("Generated prompt:", prompt)

    from context import messages
    messages.append({"role": "user", "content": prompt})

    completion = client.chat.completions.create(
        model="o1-preview-2024-09-12",  # Use an appropriate model
        messages=messages
    )
    response_content = completion.choices[0].message.content
    
    print("Raw API response:", response_content)

    # Clean the response content if necessary
    response_content = response_content.strip()
    
    print("Cleaned response content:", response_content)

    #messages.append({"role": "assistant", "content": response_content})
    return response_content  # Return the generated blog draft

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    print("Entering upload_csv function")

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.endswith('.csv'):
        try:
            csv_content = file.read().decode('utf-8')
            csv_file = StringIO(csv_content)
            csv_reader = csv.reader(csv_file)
            
            headers = next(csv_reader)
            data = [dict(zip(headers, row)) for row in csv_reader]
            
            print("CSV data:", data)

            result = analyze_csv(data)
            
            print("Analyze CSV result:", result)

            # Generate a unique ID for this result
            result_id = str(uuid.uuid4())
            generated_content[result_id] = result  # Store the result as a list of dictionaries
            
            print(f"Stored result with ID: {result_id}")

            # Return JSON response with the result ID
            return jsonify({'id': result_id}), 200
        except Exception as e:
            print(f"Error processing CSV: {str(e)}")
            return jsonify({'error': f'Error processing CSV: {str(e)}'}), 500
    else:
        return jsonify({'error': 'Invalid file format. Please upload a CSV file.'}), 400

@app.route('/generate-content', methods=['POST'])
def generate_content():
    selected_data = request.json
    
    # Generate content for each selected item concurrently
    generated_items = []
    with ThreadPoolExecutor(max_workers=5) as executor:  # Adjust max_workers as needed
        future_to_item = {executor.submit(generate_blog_draft, item['title']): item for item in selected_data}
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                content = future.result()
                generated_items.append({
                    "keyword": item['keyword'],
                    "title": item['title'],
                    "content": content
                })
            except Exception as exc:
                print(f'Generation for {item["title"]} generated an exception: {exc}')
    
    # Store the generated content with a unique ID
    content_id = str(uuid.uuid4())
    generated_content[content_id] = generated_items
    
    return jsonify({"id": content_id})

@app.route('/content')
def display_content():
    print("Entering display_content function")

    content_id = request.args.get('id')
    print(f"Requested content ID: {content_id}")

    if content_id not in generated_content:
        print("Content not found")
        return "Content not found", 404
    
    items = generated_content[content_id]
    print("Retrieved items:", items)
    print("Type of items:", type(items))
    print("Number of items:", len(items))

    # Add this block to check each item in the list
    for i, item in enumerate(items):
        print(f"Item {i}:")
        for key, value in item.items():
            print(f"  {key}: {value}")

    return render_template('parsedcsv.html', items=items)

@app.route('/blog')
def display_blog():
    content_id = request.args.get('id')
    if content_id not in generated_content:
        return "Content not found", 404
    
    blog_posts = generated_content[content_id]
    
    # Read the blog.txt file
    blog_txt_path = os.path.join(app.root_path, 'templates', 'blog.txt')
    with open(blog_txt_path, 'r') as file:
        blog_txt = file.read()
    
    return render_template('blog.html', blog_posts=blog_posts, blog_txt=blog_txt)

@app.route('/get-metatags/<int:index>')
def get_metatags(index):
    content_id = request.args.get('id')
    if content_id not in generated_content:
        return jsonify({"error": "Content not found"}), 404
    
    blog_posts = generated_content[content_id]
    if index >= len(blog_posts):
        return jsonify({"error": "Blog post index out of range"}), 404
    
    post = blog_posts[index]
    
    # Generate metatags using OpenAI API
    prompt = f"Generate SEO-friendly metatags for the following blog post title and content:\n\nTitle: {post['title']}\n\nContent: {post['content'][:500]}..."
    
    response = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[{"role": "user", "content": prompt}]
    )
    
    metatags = response.choices[0].message.content
    
    # Parse the generated metatags (assuming they're in a specific format)
    # You might need to adjust this parsing logic based on the actual output
    lines = metatags.strip().split('\n')
    title = next((line.split(': ', 1)[1] for line in lines if line.startswith('Title: ')), '')
    description = next((line.split(': ', 1)[1] for line in lines if line.startswith('Description: ')), '')
    keywords = next((line.split(': ', 1)[1] for line in lines if line.startswith('Keywords: ')), '')
    
    return jsonify({
        "title": title,
        "description": description,
        "keywords": keywords
    })

@app.route('/chat/<int:index>', methods=['POST'])
def chat(index):
    content_id = request.args.get('id')
    if content_id not in generated_content:
        return jsonify({"error": "Content not found"}), 404
    
    blog_posts = generated_content[content_id]
    if index >= len(blog_posts):
        return jsonify({"error": "Blog post index out of range"}), 404
    
    post = blog_posts[index]
    user_message = request.json['message']
    blog_content = request.json['blogContent']
    
    from context import messages
    # Generate AI response using OpenAI API
    prompt = f"""You are an AI assistant helping to edit and improve a blog post. 
    Here's the current content of the blog post:

    {blog_content}

    The user has provided the following input or question:
    {user_message}

    Please update the blog post content based on the user's input. If it's a question, 
    incorporate the answer into the blog post. If it's a suggestion for an edit, 
    make the appropriate changes. Return the entire updated blog post content.
    """
    
    response = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[{"role": "user", "content": prompt}]
    )
    
    updated_content = response.choices[0].message.content
    
    # Update the stored blog post content
    blog_posts[index]['content'] = updated_content
    
    return jsonify({"response": updated_content})

if __name__ == '__main__':
    # Use the PORT environment variable provided by Elastic Beanstalk
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

