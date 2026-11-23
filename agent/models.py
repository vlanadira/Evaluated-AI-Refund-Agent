
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from objects import Answer

load_dotenv()

model = init_chat_model(
    model="openai/gpt-oss-20b",
    model_provider="groq",
    temperature=0,
    reasoning_format="parsed"
)

structured_model = model.with_structured_output(
    Answer,
    method="json_schema",
    strict=True
)