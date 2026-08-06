import json
with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank_new.jsonl', 'r', encoding='utf-8') as f:
    qs = [json.loads(line) for line in f]
zj = [q for q in qs if q['subject'] == '计算机组成原理']
print('计组 Q1:')
print(f'  question_number: [{zj[0]["question_number"]}]')
print(f'  content: [{zj[0]["content"][:100]}]')
print(f'  options ({len(zj[0]["options"])}): {zj[0]["options"]}')
print(f'  answer: [{zj[0]["answer"]}]')
print(f'  explanation: [{zj[0]["explanation"][:150]}]')
print()
print('计组 Q2:')
print(f'  question_number: [{zj[1]["question_number"]}]')
print(f'  content: [{zj[1]["content"][:100]}]')
print(f'  answer: [{zj[1]["answer"]}]')
print(f'  explanation: [{zj[1]["explanation"][:150]}]')