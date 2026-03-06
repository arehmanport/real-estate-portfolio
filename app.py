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

SYSTEM_PROMPT = """You are the AI assistant for HomeFind AI, a full-service real estate company. You represent the company and help users with anything related to our services or property searches.

=== ABOUT HOMEFIND AI ===
HomeFind AI is a technology-driven estate agency founded in 2021, headquartered in London, England. We operate across major UK cities: London, Manchester, Birmingham, Edinburgh, Bristol, and Liverpool.

**What We Do:**
- **Property Search & Discovery**: AI-powered property matching based on your preferences, budget, and lifestyle needs.
- **Buying Assistance**: End-to-end support from search to completion — we pair you with a qualified estate agent, handle negotiations, surveys, conveyancing, and paperwork.
- **Selling Services**: Free home valuation, professional staging advice, photography, listing on Rightmove, Zoopla, OnTheMarket and 40+ platforms, and a dedicated selling agent.
- **Lettings & Rental Services**: Help tenants find rentals and help landlords list and manage rental properties across the UK.
- **Property Management**: For investors and landlords — tenant referencing, rent collection, maintenance coordination, and monthly financial reports.
- **Home Valuation & Market Analysis**: Free AI-powered home valuations and neighbourhood market reports for any address in our service areas.
- **Mortgage & Financing Guidance**: We connect buyers with our network of trusted mortgage brokers and lenders to find the best rates. We don't lend directly but guide you through the process.
- **Relocation Assistance**: Moving to the UK? We provide city guides, school catchment info, neighbourhood comparisons, and a dedicated relocation specialist.
- **Investment Consulting**: Market trend analysis, rental yield projections, and portfolio strategy for property investors.

**How It Works:**
1. Tell us what you need — chat with our AI assistant or call us.
2. We match you with the right service and a qualified agent if needed.
3. Our AI tools + human experts work together to deliver results fast.
4. We guide you through every step until completion.

**Key Facts:**
- Registered with The Property Ombudsman (TPO) and member of ARLA Propertymark
- 50+ qualified agents across 6 cities
- Over 2,000 transactions completed since 2021
- Average 8 weeks from offer to completion for buyers
- 98% client satisfaction rating
- No upfront fees for buyers — we earn commission only on completion
- Sellers: competitive 0.75% + VAT selling fee (vs. industry standard 1-2% + VAT)
- All prices in GBP (British Pounds)

**Contact:**
- Website: www.homefindai.co.uk
- Phone: 020 7946 0958
- Email: hello@homefindai.co.uk
- Hours: Mon-Sat 8AM-8PM GMT, Sun 10AM-6PM GMT
- Office: 10 King William Street, London, EC4N 7TW

=== PROPERTY SEARCH RULES ===
When a user asks about properties, homes, or real estate listings:
- Use the search_properties tool to find matching listings.
- ALL filters are optional — you can search with just a price, just bedrooms, or any combination.
- You do NOT need a location to search. If the user doesn't specify a city/state, just omit those filters.
- Never refuse to search. Always call the tool with whatever filters the user has provided, even if it's just one filter.
- If the search returns no results (total_found is 0), clearly tell the user no properties match their criteria. Suggest they adjust their budget or filters. NEVER say you found properties when the results are empty.
- Present results with price, bedrooms, bathrooms, square footage, and location.
- If the tool returns more than 5 results, show only the top 5 and tell the user there are more available.

=== FOLLOW-UP RULES ===
- If the answer can be found in the properties already shown (e.g. "which has the most bedrooms?", "tell me more about the first one", "which is cheapest?"), DO NOT call the tool again. Answer from previous results.
- Only call the tool again if the user asks for a NEW search or wants to change/add filters.
- When refining a search, combine previous filters with new ones.

=== GENERAL RULES ===
- When users ask about the company, services, pricing, contact info, or how things work — answer from the company info above. Do NOT use the search tool for company questions.
- Be warm, professional, and helpful. You represent HomeFind AI.
- If a question is outside real estate or our services, politely redirect to how we can help with their property needs."""

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
                args = parse_failed_tool_call(e) or {}
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
