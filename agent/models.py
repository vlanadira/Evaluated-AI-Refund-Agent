
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from objects import Answer

load_dotenv()

model = init_chat_model(
    model="gpt-6-luna",
    model_provider="openai",
    temperature=0,
    reasoning_effort="none",
    use_responses_api=False,
)

structured_model = model.with_structured_output(
    Answer,
    method="json_schema",
    strict=True
)