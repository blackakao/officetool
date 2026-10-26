"""MyTool 프로세스 내부에서 실행하는 오프라인 회의록 모델."""
import copy
import json
import os
from pathlib import Path

from data_paths import runtime_directory
from business_planning.minutes import SYSTEM_PROMPT, parse_response, validate

MODEL_ID = 'Qwen/Qwen3-0.6B'
MODEL_REVISION = 'c1899de289a04d12100db370d81485cdf75e47ca'
MODEL_FILES = ['config.json', 'generation_config.json', 'model.safetensors',
               'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt', 'LICENSE']
LOCAL_STYLE = '''
한국어로 작성한다. text에는 이름이나 직책을 넣지 말고 발언 문장만 작성한다.
주요 논의(notes)와 참석자별 의견(opinions)의 구체적인 내용을 반드시 발언에 포함한다.
첫 발언은 진행자가 안건의 구체적인 주제를 소개한다.
두 번째 발언은 다른 참석자가 메모에 나온 구체적인 문제와 의견을 설명한다.
마지막 발언은 추가로 검토할 내용을 정리한다. 자신에게 질문하지 않는다.
예산이나 실행 여부가 미정이면 아직 정하지 않았다고 말한다.
최소 세 개 발언을 작성한다. 입력에 없는 결론이나 약속은 추가하지 않는다.
'''


def model_directory(root=None):
    return runtime_directory(root) / 'business_planning' / 'models' / 'qwen3-0.6b'


def model_ready(directory):
    directory = Path(directory)
    return all((directory / name).is_file() for name in MODEL_FILES)


def download_model(directory, progress=lambda _: None):
    # Only this explicit setup action may access the network; no meeting data is passed.
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ValueError('내장 AI 실행 패키지를 설치하세요: python -m pip install -r requirements-local-ai.txt') from None
    progress('내장 AI 모델 다운로드 중 (약 1.5GB, 최초 1회)…')
    snapshot_download(MODEL_ID, revision=MODEL_REVISION, local_dir=str(directory),
                      allow_patterns=MODEL_FILES, token=False)
    if not model_ready(directory):
        raise ValueError('모델 다운로드가 완료되지 않았습니다. 다시 다운로드해 주세요.')
    progress('내장 AI 모델 준비 완료')


def load_engine(directory):
    if not model_ready(directory):
        raise ValueError('AI 설정에서 내장 모델을 먼저 다운로드하세요.')
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        raise ValueError('내장 AI 실행 패키지를 설치하세요: python -m pip install -r requirements-local-ai.txt') from None
    tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        str(directory), local_files_only=True, trust_remote_code=False,
        use_safetensors=True, torch_dtype=torch.float32)
    model.eval()
    return tokenizer, model


def complete(tokenizer, model, messages, cancelled, max_new_tokens=1800):
    import torch
    from transformers import StoppingCriteria, StoppingCriteriaList

    class Cancelled(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):
            return cancelled()

    text = tokenizer.apply_chat_template(messages, tokenize=False,
                                        add_generation_prompt=True, enable_thinking=False)
    inputs = tokenizer(text, return_tensors='pt')
    if inputs['input_ids'].shape[-1] > 6000:
        raise ValueError('입력 내용이 내장 AI 한도를 초과했습니다. 프롬프트를 줄여 주세요.')
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=True,
                                temperature=0.7, top_p=0.8, top_k=20, repetition_penalty=1.1,
                                stopping_criteria=StoppingCriteriaList([Cancelled()]))
    if cancelled():
        raise ValueError('AI 작성을 취소했습니다. 기존 내용은 유지됩니다.')
    return tokenizer.decode(output[0][inputs['input_ids'].shape[-1]:], skip_special_tokens=True)


def generate_local(meeting, directory=None, progress=lambda _: None, cancelled=lambda: False,
                   loader=load_engine, completion=complete):
    validate(meeting)
    if meeting.get('version', 1) == 2 and not meeting.get('prompt', '').strip():
        raise ValueError('회의 내용과 참석자 역할을 프롬프트에 입력하세요.')
    progress('내장 AI 모델을 메모리에 불러오는 중…')
    tokenizer, model = loader(directory or model_directory())
    results = {}
    try:
        if meeting.get('version', 1) == 2:
            return generate_from_prompt(meeting, tokenizer, model, progress, cancelled, completion)
        # Short local IDs reduce copying mistakes in a small model. Each agenda is isolated.
        for index, agenda in enumerate(meeting['agendas'], 1):
            if cancelled():
                raise ValueError('AI 작성을 취소했습니다. 기존 내용은 유지됩니다.')
            progress(f'내장 AI 작성 중: 안건 {index}/{len(meeting["agendas"])}')
            sample = copy.deepcopy(meeting)
            sample['attendees'] = [p for p in sample['attendees'] if p['present']]
            for number, person in enumerate(sample['attendees'], 1):
                person['id'] = f'p{number}'
            item = {k: v for k, v in agenda.items() if k not in ('draft', 'final')}
            item['id'] = 'a1'
            sample['agendas'] = [item]
            payload = {k: sample[k] for k in ['title', 'date', 'attendees', 'agendas']}
            messages = [dict(role='system', content=SYSTEM_PROMPT + LOCAL_STYLE),
                        dict(role='user', content=json.dumps(payload, ensure_ascii=False))]
            content = completion(tokenizer, model, messages, cancelled).strip()
            if content.startswith('```') and content.endswith('```'):
                content = '\n'.join(content.splitlines()[1:-1])
            try:
                results[agenda['id']] = parse_response(content, sample)['a1']
            except (ValueError, TypeError, KeyError, AttributeError):
                raise ValueError(f'{index}번 안건의 AI 응답 형식이 올바르지 않습니다. '
                                 '기존 내용은 유지됩니다. 메모를 간결하게 정리해 다시 작성하세요.') from None
        return results
    finally:
        del model, tokenizer


def generate_from_prompt(meeting, tokenizer, model, progress, cancelled, completion):
    people = copy.deepcopy([p for p in meeting['attendees'] if p['present']])
    total = max(6, len(people) * 2)
    speeches = []
    for turn in range(total):
        if cancelled():
            raise ValueError('AI 작성을 취소했습니다. 기존 내용은 유지됩니다.')
        person = people[turn % len(people)]
        stage = ('공손한 시작 인사와 회의 주제 소개' if turn == 0 else
                 '새로운 사실이나 결론을 추가하지 않는 감사 인사 한 문장' if turn == total - 1 else
                 '직전 질문에 답하되 모르는 내용은 확인이 필요하다고 설명' if turn % len(people) == 0 else
                 '직전 발언에 관해 확인이 필요한 점을 묻는 질문 한 문장 (물음표로 끝내기)')
        history = '\n'.join(
            f"{next(p['name'] for p in people if p['id'] == s['attendee_id'])}: {s['text']}"
            for s in speeches)
        roster = '\n'.join(f"{p['name']} / {p['position']} / {p['role']}" for p in people)
        prompt = (
            f"회의 제목: {meeting['title']}\n참석자:\n{roster}\n\n"
            f"작성 요청:\n{meeting['prompt']}\n\n"
            f"지금까지의 대화:\n{history or '(회의 시작 전)'}\n\n"
            f"이어서 {person['name']} 님이 직접 말할 차례입니다. {stage}를 해 주세요.\n"
            "역할을 설명하거나 요청을 반복하지 말고, 실제로 말하듯 대사만 작성하세요.")
        messages = [dict(role='system', content='''당신은 운영위원회 회의의 참석자입니다.
지정된 참석자가 직접 말하는 한국어 존댓말 대사 1~3문장만 작성하세요.
작성 요청의 역할과 말투를 따르고 지금까지의 대화에 자연스럽게 이어 답하세요.
발언자 이름, 역할 해설, JSON, 다른 사람의 대사는 출력하지 마세요.
예: 역할이 공손한 진행자라면 "A는 공손한 진행자입니다"가 아니라 "참석해 주셔서 감사합니다"처럼 말하세요.
입력에 없는 사실, 수치, 법률 조항, 승인, 의결 결과를 만들지 마세요.
적법성 검토 요청만으로 적법하다고 결론내리지 말고 확인할 자료에 관해 이야기하세요.
실제 발언이 아닌 사용자가 검토할 가상 초안입니다.'''),
                    dict(role='user', content=prompt)]
        progress(f'대화형 회의록 작성 중: {turn + 1}/{total} ({person["name"]})')
        if completion is complete:
            content = complete(tokenizer, model, messages, cancelled, max_new_tokens=220).strip()
        else:
            content = completion(tokenizer, model, messages, cancelled).strip()
        if cancelled():
            raise ValueError('AI 작성을 취소했습니다. 기존 내용은 유지됩니다.')
        if content.startswith('```') and content.endswith('```'):
            content = '\n'.join(content.splitlines()[1:-1]).strip()
        if content.startswith('{'):
            try:
                envelope = json.loads(content)
                if envelope.get('name', person['name']) != person['name']:
                    raise ValueError()
                content = envelope.get('message', envelope.get('text', envelope.get('content')))
                if not isinstance(content, str):
                    raise ValueError()
                content = content.strip()
            except (ValueError, AttributeError):
                raise ValueError('AI 발언 형식이 올바르지 않습니다. 다시 작성해 주세요.') from None
        # The app assigns speakers; the model cannot invent a speaker or change the order.
        prefix = person['name'] + ':'
        if content.startswith(prefix):
            content = content[len(prefix):].strip()
        if not content or content.startswith(('{', '[', '```')) or any(
                ':' in line or '：' in line for line in content.splitlines()):
            raise ValueError('AI 발언 형식이 올바르지 않습니다. 다시 작성해 주세요. 기존 내용은 유지됩니다.')
        speeches.append({'attendee_id': person['id'], 'text': content.strip('“”"')})
    sample = {'attendees': people, 'agendas': [{'id': 'conversation'}]}
    wrapped = json.dumps({'agendas': [{'id': 'conversation', 'speeches': speeches}]})
    return parse_response(wrapped, sample)['conversation']


if __name__ == '__main__':
    download_model(model_directory(), print)
