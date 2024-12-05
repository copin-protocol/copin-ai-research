import base64
from io import BytesIO
import config
import logging

import tiktoken
import openai
from analyze_func import analyze_trader


# setup openai
openai.api_key = config.openai_api_key

logger = logging.getLogger(__name__)


OPENAI_COMPLETION_OPTIONS = {
    "temperature": 0.7,
    "max_tokens": 1000,
    "top_p": 1,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "request_timeout": 60.0,
}


class ChatGPT:
    def __init__(self, model="gpt-4o-mini"):
        assert model in {"gpt-4o-mini", "gpt-4o", "gpt-4"}, f"Unknown model: {model}"
        self.model = model

    async def send_message(self, message, dialog_messages=[], chat_mode="assistant"):
        if chat_mode not in config.chat_modes.keys():
            raise ValueError(f"Chat mode {chat_mode} is not supported")

        n_dialog_messages_before = len(dialog_messages)
        answer = None
        while answer is None:
            try:
                if self.model in {"gpt-4o-mini", "gpt-4o", "gpt-4"}:
                    messages = self._generate_prompt_messages(
                        message, dialog_messages, chat_mode
                    )

                    r = await openai.ChatCompletion.acreate(
                        model=self.model, messages=messages, **OPENAI_COMPLETION_OPTIONS
                    )
                    answer = r.choices[0].message["content"]
                # elif self.model == "text-davinci-003":
                #     prompt = self._generate_prompt(message, dialog_messages, chat_mode)
                #     r = await openai.Completion.acreate(
                #         engine=self.model,
                #         prompt=prompt,
                #         **OPENAI_COMPLETION_OPTIONS
                #     )
                #     answer = r.choices[0].text
                else:
                    raise ValueError(f"Unknown model: {self.model}")

                answer = self._postprocess_answer(answer)
                n_input_tokens, n_output_tokens = (
                    r.usage.prompt_tokens,
                    r.usage.completion_tokens,
                )
            except Exception as e:  # too many tokens
                if len(dialog_messages) == 0:
                    raise ValueError(
                        "Dialog messages is reduced to zero, but still has too many tokens to make completion"
                    ) from e

                # forget first message in dialog_messages
                dialog_messages = dialog_messages[1:]

        n_first_dialog_messages_removed = n_dialog_messages_before - len(
            dialog_messages
        )

        return (
            answer,
            (n_input_tokens, n_output_tokens),
            n_first_dialog_messages_removed,
        )

    async def send_message_stream(
        self, message, dialog_messages=[], chat_mode="assistant"
    ):
        if chat_mode not in config.chat_modes.keys():
            raise ValueError(f"Chat mode {chat_mode} is not supported")
        elif chat_mode =="Copin Analysys":
            account = next(iter(dialog_messages), None)
            stats = analyze_trader(account,"BINGX")
            result= {}
            result['reverse_copy'] = stats[0]
            result['leverage'] = stats[1]
            result['take_profit'] = stats[2]
            result['stop_loss'] = stats[3]
            messages = self._generate_prompt_copin(
                        message, result, chat_mode
                    )
            r_gen = await openai.ChatCompletion.acreate(
                        model=self.model,
                        messages=messages,
                        stream=True,
                        **OPENAI_COMPLETION_OPTIONS,
                    )

            answer = ""
            async for r_item in r_gen:
                delta = r_item.choices[0].delta

                if "content" in delta:
                    answer += delta.content
                    n_input_tokens, n_output_tokens = (
                        self._count_tokens_from_messages(
                            messages, answer, model=self.model
                        )
                    )
                    n_first_dialog_messages_removed = 0

                    yield "not_finished", answer, (
                        n_input_tokens,
                        n_output_tokens,
                    ), n_first_dialog_messages_removed
            
        else:
            n_dialog_messages_before = len(dialog_messages)
            answer = None
            try:
                if self.model in {"gpt-4o-mini", "gpt-4o", "gpt-4"}:
                    messages = self._generate_prompt_messages(
                        message, dialog_messages, chat_mode
                    )

                    r_gen = await openai.ChatCompletion.acreate(
                        model=self.model,
                        messages=messages,
                        stream=True,
                        **OPENAI_COMPLETION_OPTIONS,
                    )

                    answer = ""
                    async for r_item in r_gen:
                        delta = r_item.choices[0].delta

                        if "content" in delta:
                            answer += delta.content
                            n_input_tokens, n_output_tokens = (
                                self._count_tokens_from_messages(
                                    messages, answer, model=self.model
                                )
                            )
                            n_first_dialog_messages_removed = 0

                            yield "not_finished", answer, (
                                n_input_tokens,
                                n_output_tokens,
                            ), n_first_dialog_messages_removed

                # elif self.model == "text-davinci-003":
                #     prompt = self._generate_prompt(message, dialog_messages, chat_mode)
                #     r_gen = await openai.Completion.acreate(
                #         engine=self.model,
                #         prompt=prompt,
                #         stream=True,
                #         **OPENAI_COMPLETION_OPTIONS
                #     )

                #     answer = ""
                #     async for r_item in r_gen:
                #         answer += r_item.choices[0].text
                #         n_input_tokens, n_output_tokens = self._count_tokens_from_prompt(prompt, answer, model=self.model)
                #         n_first_dialog_messages_removed = n_dialog_messages_before - len(dialog_messages)
                #         yield "not_finished", answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed

                answer = self._postprocess_answer(answer)

            except Exception as e:  # too many tokens
                if len(dialog_messages) == 0:
                    raise e

                # forget first message in dialog_messages
                dialog_messages = dialog_messages[1:]

        yield "finished", answer, (
            n_input_tokens,
            n_output_tokens,
        ), n_first_dialog_messages_removed  # sending final answer

    def _encode_image(self, image_buffer: BytesIO) -> bytes:
        return base64.b64encode(image_buffer.read()).decode("utf-8")

    def _generate_prompt(self, message, dialog_messages, chat_mode):
        prompt = config.chat_modes[chat_mode]["prompt_start"]
        prompt += "\n\n"

        # add chat context
        if len(dialog_messages) > 0:
            prompt += "Chat:\n"
            for dialog_message in dialog_messages:
                prompt += f"User: {dialog_message['user']}\n"
                prompt += f"Assistant: {dialog_message['bot']}\n"

        # current message
        prompt += f"User: {message}\n"
        prompt += "Assistant: "

        return prompt
    
    def _generate_prompt_copin(
        self, message, stats, chat_mode
    ):
        prompt = config.chat_modes[chat_mode]["prompt_start"]
        prompt += "\n\n"

        # add chat context
        if len(stats) > 0:
            prompt += "Chat:\n"
            
            prompt += f"Stats: {stats}\n"

        # current message
        prompt += f"User: {message}\n"
        prompt += "Assistant: "

        return prompt

    def _generate_prompt_messages(
        self, message, dialog_messages, chat_mode, image_buffer: BytesIO = None
    ):
        prompt = config.chat_modes[chat_mode]["prompt_start"]
            
        messages = [{"role": "system", "content": prompt}]

        for dialog_message in dialog_messages:
            messages.append({"role": "user", "content": dialog_message["user"]})
            messages.append({"role": "assistant", "content": dialog_message["bot"]})

        if image_buffer is not None:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": message,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{self._encode_image(image_buffer)}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": message})

        return messages

    def _postprocess_answer(self, answer):
        answer = answer.strip()
        return answer

    def _count_tokens_from_messages(self, messages, answer, model="gpt-3.5-turbo"):
        encoding = tiktoken.encoding_for_model(model)

        tokens_per_message = 3

        # input
        n_input_tokens = 0
        for message in messages:
            n_input_tokens += tokens_per_message
            if isinstance(message["content"], list):
                for sub_message in message["content"]:
                    if "type" in sub_message:
                        if sub_message["type"] == "text":
                            n_input_tokens += len(encoding.encode(sub_message["text"]))
                        elif sub_message["type"] == "image_url":
                            pass
            else:
                if "type" in message:
                    if message["type"] == "text":
                        n_input_tokens += len(encoding.encode(message["text"]))
                    elif message["type"] == "image_url":
                        pass

        n_input_tokens += 2

        # output
        n_output_tokens = 1 + len(encoding.encode(answer))

        return n_input_tokens, n_output_tokens
