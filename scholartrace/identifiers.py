"""Normalize ORCID inputs and validate ISO 7064 MOD 11-2 checksums."""
import re


def orcid_id(value):
    value = value.strip()
    explicit = bool(re.search(r'orcid', value, re.I))
    candidate = re.sub(r'^(?:https?://(?:www\.)?orcid\.org/|orcid:\s*)', '', value, flags=re.I).rstrip('/')
    looks_numeric = bool(re.fullmatch(r'[\dXx-]+', candidate))
    if not explicit and not looks_numeric:
        return None
    if not re.fullmatch(r'(?:\d{4}-\d{4}-\d{4}-\d{3}[\dXx]|\d{15}[\dXx])', candidate):
        raise ValueError('ORCID 格式无效，请输入 16 位编号或 orcid.org 链接')
    digits = candidate.replace('-', '').upper()
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    if digits[-1] != ('X' if check == 10 else str(check)):
        raise ValueError('ORCID 校验位不正确，请检查是否输错编号')
    return '-'.join(digits[i:i+4] for i in range(0,16,4))
