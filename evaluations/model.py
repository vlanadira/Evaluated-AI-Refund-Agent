from dotenv import load_dotenv
from deepeval.models import DeepEvalBaseLLM
from langchain_openai import ChatOpenAI

load_dotenv()


class OpenAIEvalModel(DeepEvalBaseLLM):
    def load_model(self):
        return ChatOpenAI(
            model=self.name,
            temperature=0,
            max_completion_tokens=512,
            reasoning_effort="none",
            use_responses_api=False,
        )

    def generate(self, prompt, schema=None):
        model = self.model
        if schema is not None:
            model = model.with_structured_output(schema, method="json_schema")
        response = model.invoke(prompt)
        return response if schema is not None else response.content

    async def a_generate(self, prompt, schema=None):
        model = self.model
        if schema is not None:
            model = model.with_structured_output(schema, method="json_schema")
        response = await model.ainvoke(prompt)
        return response if schema is not None else response.content

    def get_model_name(self):
        return self.name


eval_model = OpenAIEvalModel(model="gpt-6-luna")
