import json
from bs4 import BeautifulSoup

def extract_game_lists_to_json(html_source, output_json_path="game_lists.json"):
    """
    HTML 소스에서 id="game-lists"를 찾아 li 태그의 data-game-idx와 label 텍스트를 추출하여 JSON 파일로 저장합니다.
    """
    # HTML 파싱
    soup = BeautifulSoup(html_source, 'html.parser')

    # id가 game-lists인 ul 태그 찾기
    ul_tag = soup.find('ul', id='game-lists')

    if not ul_tag:
        print("❌ id='game-lists'인 <ul> 태그를 찾을 수 없습니다.")
        return

    result_list = []

    # ul 내부의 모든 li 태그 순회
    for li in ul_tag.find_all('li'):
        idx = li.get('data-game-idx')  # data-game-idx 값 가져오기
        label_tag = li.find('label')   # 내부의 label 태그 찾기

        # idx와 label 태그가 모두 존재하는 경우에만 추출
        if idx and label_tag:
            name = label_tag.get_text(strip=True) # label의 텍스트 추출 (공백 제거)

            result_list.append({
                "idx": idx,
                "name": name
            })

    # 결과를 JSON 파일로 저장 (ensure_ascii=False로 설정해야 한글이 깨지지 않고 저장됩니다)
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(result_list, f, ensure_ascii=False, indent=2)

    print(f"✨ 성공적으로 {len(result_list)}개의 데이터를 추출하여 '{output_json_path}' 파일로 저장했습니다.")

# ==========================================================
# 실행 예시
# ==========================================================
if __name__ == "__main__":
    # 1. 파일에서 HTML을 읽어오는 경우 (일반적인 사용법)
    with open("idfarm.html", "r", encoding="utf-8") as f:
        html_content = f.read()
        extract_game_lists_to_json(html_content, "game_lists.json")
