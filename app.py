"""
Flask app with Groq-powered real estate chatbot.
"""

import json
import os
import re
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from groq import Groq, BadRequestError

from tools import SEARCH_TOOL_SCHEMA, search_properties, get_property_by_id, get_all_properties

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", uuid.uuid4().hex)

# Configure Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

# Primary model + 2 fallbacks
MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

SYSTEM_PROMPT = """You are a friendly and knowledgeable real estate assistant. Your job is to help users find their perfect property.

When a user asks about properties, homes, or real estate:
- Use the search_properties tool to find matching listings
- ALL filters are optional — you can search with just a price, just bedrooms, or any combination
- You do NOT need a location to search. If the user doesn't specify a city/state, just omit those filters and search across all locations.
- Never refuse to search. Always call the tool with whatever filters the user has provided, even if it's just one filter.
- If the search returns no results (total_found is 0), clearly tell the user no properties match their criteria. Suggest they adjust their budget or filters. NEVER say you found properties when the results are empty.
- Present the results with price, bedrooms, bathrooms, square footage, and location.
- If the tool returns more than 5 results, show only the top 5 and tell the user there are more available — ask if they'd like to see more or refine their search.
- Be conversational and enthusiastic about helping them find their dream home

When the user asks follow-up questions:
- If the answer can be found in the properties already shown (e.g. "which has the most bedrooms?", "tell me more about the first one", "which is cheapest?"), DO NOT call the tool again. Just answer from the previous results in the conversation.
- Only call the tool again if the user asks for a NEW search or wants to change/add filters (e.g. "show me homes in Houston", "increase my budget to 500k").
- When refining a search, combine previous filters with new ones. For example if user first asked for "homes under 400k" and then says "any in Houston?", search with BOTH max_price=400000 AND city=Houston.
Always be helpful, professional, and encouraging."""

# Groq tool definition (OpenAI-compatible format)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": SEARCH_TOOL_SCHEMA["name"],
            "description": SEARCH_TOOL_SCHEMA["description"],
            "parameters": SEARCH_TOOL_SCHEMA["parameters"],
        },
    }
]


def get_chat_history():
    """Get or initialize conversation history from session."""
    if "messages" not in session:
        session["messages"] = []
    return session["messages"]


MAX_HISTORY = 20


def parse_failed_tool_call(error):
    """Extract args from a malformed tool call in Groq's failed_generation."""
    error_str = str(error)
    match = re.search(r'\{[^{}]+\}', error_str)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def call_groq(messages, model, tools=None, max_tokens=1024):
    """Call Groq API with automatic model fallback."""
    last_error = None
    models_to_try = MODELS[MODELS.index(model):] if model in MODELS else MODELS

    for m in models_to_try:
        try:
            kwargs = {
                "model": m,
                "messages": messages,
                "max_tokens": max_tokens,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            response = client.chat.completions.create(**kwargs)
            if m != models_to_try[0]:
                print(f"Fallback: using {m} (primary model unavailable)")
            return response
        except BadRequestError:
            raise
        except Exception as e:
            last_error = e
            print(f"Model {m} failed: {e}, trying next...")
            continue

    raise last_error


def call_llm(user_message):
    """Send message to Groq with tool support and full conversation history."""
    history = get_chat_history()
    history.append({"role": "user", "content": user_message})

    # Build messages — include full history (with tool calls/results) for context
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-MAX_HISTORY:])

    properties = []
    max_tool_rounds = 3

    for _ in range(max_tool_rounds):
        try:
            response = call_groq(messages, MODELS[0], tools=TOOLS)
        except BadRequestError as e:
            if "tool_use_failed" in str(e):
                args = parse_failed_tool_call(e)
                if args:
                    args.setdefault("limit", 20)
                    properties = search_properties(**args)
                    summary_msg = (
                        f"[Tool returned {len(properties)} properties: "
                        f"{json.dumps([{k: r.get(k) for k in ('address','city','state','price','bedrooms','bathrooms','sqft')} for r in properties])}]"
                    )
                    messages.append({"role": "assistant", "content": summary_msg})
                    messages.append({"role": "user", "content":
                        "Present the top 5 properties. If there are more, tell the user how many more are available."
                    })
                    response = call_groq(messages, MODELS[0])
                    reply_text = response.choices[0].message.content or (
                        "Here are some properties I found!" if properties else
                        "Sorry, I couldn't find any properties matching your criteria. Try adjusting your budget or filters."
                    )
                    history.append({"role": "assistant", "content": f"{reply_text}\n\n[Search results: {summary_msg}]"})
                    session["messages"] = history
                    session.modified = True
                    return reply_text, properties[:5]
            raise

        resp_msg = response.choices[0].message

        if resp_msg.tool_calls:
            # Store the assistant's tool call in history for context
            tool_call_entry = {
                "role": "assistant",
                "content": resp_msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in resp_msg.tool_calls
                ],
            }
            messages.append(tool_call_entry)
            history.append(tool_call_entry)

            for tc in resp_msg.tool_calls:
                args = json.loads(tc.function.arguments)
                args.setdefault("limit", 20)
                results = search_properties(**args)
                properties = results

                slim = [
                    {k: r.get(k) for k in ("address", "city", "state", "price", "bedrooms", "bathrooms", "sqft")}
                    for r in results
                ]
                tool_content = {
                    "total_found": len(results),
                    "showing": slim[:5],
                }
                if len(results) > 5:
                    tool_content["note"] = f"There are {len(results) - 5} more matching properties available."

                tool_result = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_content),
                }
                messages.append(tool_result)
                history.append(tool_result)
        else:
            break

    if resp_msg.content:
        reply_text = resp_msg.content
    elif properties:
        reply_text = "Here are some properties I found for you!"
    else:
        reply_text = "Sorry, I couldn't find any properties matching your criteria. Try adjusting your budget or filters."

    history.append({"role": "assistant", "content": reply_text})
    session["messages"] = history
    session.modified = True

    return reply_text, properties[:5]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/properties")
def properties_page():
    props = get_all_properties()
    return render_template("properties.html", properties=props)


@app.route("/property/<int:property_id>")
def property_detail(property_id):
    prop = get_property_by_id(property_id)
    if not prop:
        return "Property not found", 404
    return render_template("property.html", property=prop)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Please type a message.", "properties": []})

    try:
        reply, properties = call_llm(user_message)
        # Clean NaN values for JSON serialization
        clean_props = []
        for p in properties:
            clean = {}
            for k, v in p.items():
                if isinstance(v, float) and (v != v):  # NaN check
                    clean[k] = None
                else:
                    clean[k] = v
            clean_props.append(clean)
        return jsonify({"reply": reply, "properties": clean_props})
    except Exception as e:
        error_msg = str(e)
        print(f"Chat error: {error_msg}")
        if "429" in error_msg or "rate" in error_msg.lower():
            reply = "The AI service is temporarily rate-limited. Please wait a moment and try again."
        elif "API key" in error_msg or "401" in error_msg or "auth" in error_msg.lower():
            reply = "There's an issue with the API key configuration. Please check your GROQ_API_KEY in the .env file."
        else:
            reply = f"Sorry, I encountered an error: {error_msg[:200]}"
        return jsonify({"reply": reply, "properties": []}), 500


@app.route("/reset", methods=["POST"])
def reset():
    session.pop("messages", None)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
