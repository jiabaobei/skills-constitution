"""完整复现 ci.yml 的两个校验步骤"""
import json
import re

# --- 步骤1: Validate committed skill tree index ---
tree = json.load(open('skill_tree.json', encoding='utf-8'))
assert tree['total'] > 0, 'skill_tree.json indexed 0 skills'
assert len(tree['categories']) > 0, 'No categories in index'
cat_sum = sum(len(v) for v in tree['categories'].values())
assert cat_sum >= tree['total'], f'Index inconsistent: category sum ({cat_sum}) < total ({tree["total"]})'
assert 'version' in tree and tree['version'], 'skill_tree.json missing version'
print(f'✓ step1 索引校验通过: {tree["total"]} skills, {len(tree["categories"])} categories (cat_sum={cat_sum}), version={tree["version"]}')

# --- 步骤2: Validate SKILL.md frontmatter & version consistency ---
content = open('SKILL.md', encoding='utf-8').read()
m = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
assert m, 'SKILL.md missing YAML frontmatter'
fm = m.group(1)
mv = re.search(r'^version:\s*(\S+)', fm, re.MULTILINE)
assert mv, 'SKILL.md frontmatter missing version'
assert tree.get('version') == mv.group(1), \
    f'version mismatch: SKILL.md={mv.group(1)} vs skill_tree.json={tree.get("version")}'
print(f'✓ step2 版本一致性通过: SKILL.md={mv.group(1)} == skill_tree.json={tree.get("version")}')

print('\n✅ 全部 CI 校验通过，可推送')
