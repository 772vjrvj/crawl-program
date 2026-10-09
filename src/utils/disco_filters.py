"""디스코 화면 설정과 POST 폼 변환. 네트워크 요청은 하지 않습니다."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


PYEONG_TO_SQM = Decimal("3.305785")


def _checks(options):
    return [
        {"name": name, "code": code, "type": "checkbox", "value": False}
        for name, code in options
    ]


def _range(name, low, high):
    return {
        "name": name, "type": "two_input",
        "items": [
            {"name": "최소", "code": low, "type": "input", "value": ""},
            {"name": "최대", "code": high, "type": "input", "value": ""},
        ],
    }


def default_disco_filters():
    property_groups = [
        ("상가·사무실·공장", "12,10,11,17,19,18,15", [
            ("상업용건물", "12"), ("상가·사무실", "10,11"),
            ("공장·창고", "17,19"), ("지식산업센터", "18"), ("숙박시설", "15"),
        ]),
        ("아파트·오피스텔", "0,1,2,20", [
            ("아파트", "0"), ("주상복합", "1"),
            ("오피스텔", "2"), ("생활숙박시설", "20"),
        ]),
        ("빌라·주택", "7,8,3,5,4,6", [
            ("연립", "7"), ("다세대", "8"), ("단독·전원주택", "3,5"),
            ("다가구", "4"), ("상가주택", "6"),
        ]),
        ("토지", "16", [("토지", "16")]),
    ]
    use_groups = [
        ("주거지역", [("1종전용 주거", "1"), ("2종전용 주거", "2"),
                    ("1종 일반 주거", "3"), ("2종 일반 주거", "4"),
                    ("3종 일반 주거", "5"), ("준 주거", "6")]),
        ("상업지역", [("중심 상업", "7"), ("일반 상업", "8"),
                    ("근린 상업", "9"), ("유통 상업", "10")]),
        ("공업지역", [("전용 공업", "11"), ("일반 공업", "12"), ("준 공업", "13")]),
        ("녹지지역", [("보전녹지", "14"), ("생산녹지", "15"), ("자연녹지", "16")]),
        ("관리지역", [("계획관리", "17"), ("생산관리", "18"), ("보전관리", "19")]),
        ("기타", [("농림", "20"), ("자연환경 보전", "21")]),
    ]
    area = _range("면적 범위", "minArea", "maxArea")
    area.update({"type": "disco_area", "code": "area", "areaUnit": "pyeong",
                 "exclusiveAreaOnly": False})
    return [
        {"name": "매물 유형", "code": "randType", "type": "disco_property",
         "selectedGroup": "all", "children": [
             {"name": name, "code": code, "items": _checks(options)}
             for name, code, options in property_groups
         ]},
        {"name": "거래 유형", "code": "deal_type", "type": "disco_multi",
         "items": _checks([("매매", "0"), ("전세", "1"), ("월세", "2")])},
        _range("매매가 (만원)", "minPrice", "maxPrice"),
        _range("보증금 / 전세금 (만원)", "minDeposit", "maxDeposit"),
        _range("월세 (만원)", "minMonthly", "maxMonthly"),
        area,
        {"name": "용도지역", "code": "useArea", "type": "disco_use_area",
         "children": [{"name": name, "code": "useArea", "type": "disco_multi",
                       "items": _checks(options)} for name, options in use_groups]},
    ]


def select_property_group(node, group_code):
    """분류를 전환하면 다른 분류를 해제하고 새 분류 전체를 선택합니다."""
    node["selectedGroup"] = group_code
    for group in node["children"]:
        for item in group["items"]:
            item["value"] = group["code"] == group_code


def _number(value, label):
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"{label}: 숫자를 입력해주세요.") from None
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label}: 0 이상의 숫자를 입력해주세요.")
    return number


def _text(number):
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def build_disco_form(filters):
    """반복 키를 보존하는 [(키, 값), ...] 형태로 반환합니다."""
    form = []
    for node in filters:
        kind = node["type"]
        if kind == "disco_property":
            active = node.get("selectedGroup", "all")
            if active == "all":
                continue  # 전체는 randType/selectedCategory를 생략
            group = next((g for g in node["children"] if g["code"] == active), None)
            if group is None:
                raise ValueError("매물 유형을 다시 선택해주세요.")
            codes = []
            for item in group["items"]:
                if item["value"]:
                    codes.extend(item["code"].split(","))
            if not codes:
                raise ValueError("매물 구분을 하나 이상 선택하거나 전체유형을 선택해주세요.")
            form.extend([
                ("randType", ",".join(dict.fromkeys(codes))),
                ("selectedCategory", group["code"]),
            ])
        elif kind == "disco_multi":
            checked = [item for item in node["items"] if item["value"]]
            # 모든 거래유형 선택도 전체와 동일하게 키를 생략
            if len(checked) != len(node["items"]):
                form.extend((node["code"], item["code"]) for item in checked)
        elif kind == "disco_use_area":
            for group in node["children"]:
                form.extend(("useArea", item["code"]) for item in group["items"] if item["value"])
        elif kind in ("two_input", "disco_area"):
            numbers = [_number(item["value"], node["name"]) for item in node["items"]]
            low, high = numbers
            if low is not None and high is not None and low > high:
                raise ValueError(f"{node['name']}: 최소값이 최대값보다 큽니다.")
            for item, value in zip(node["items"], numbers):
                if kind == "disco_area" and node["areaUnit"] == "pyeong" and value is not None:
                    value = (value * PYEONG_TO_SQM).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                form.append((item["code"], "null" if value is None else _text(value)))
            if kind == "disco_area":
                form.extend([
                    ("areaUnit", node["areaUnit"]),
                    ("exclusiveAreaOnly", "true" if node["exclusiveAreaOnly"] else "false"),
                ])
    form.extend([("approvalYear", "null"), ("ownerVerifiedOnly", "")])
    return form


def filter_summary(filters):
    lines = []
    for node in filters:
        kind = node["type"]
        if kind == "disco_property":
            group = next((g for g in node["children"] if g["code"] == node["selectedGroup"]), None)
            names = [i["name"] for i in group["items"] if i["value"]] if group else []
            lines.append("매물 유형 : " + (", ".join(names) if names else "전체"))
        elif kind == "disco_multi":
            names = [i["name"] for i in node["items"] if i["value"]]
            lines.append("거래 유형 : " + (", ".join(names) if names else "전체"))
        elif kind == "disco_use_area":
            names = [i["name"] for g in node["children"] for i in g["items"] if i["value"]]
            lines.append("용도지역 : " + (", ".join(names) if names else "전체"))
        elif kind in ("two_input", "disco_area"):
            low, high = [str(i["value"]).strip() for i in node["items"]]
            if low or high:
                unit = "평" if node.get("areaUnit") == "pyeong" else "㎡" if kind == "disco_area" else "만원"
                lines.append(f"{node['name']} : {low or '제한 없음'} ~ {high or '제한 없음'} {unit}")
            if kind == "disco_area" and node["exclusiveAreaOnly"]:
                lines.append("전용면적 기준으로 찾기 : 선택")
    return "\n".join(lines)
