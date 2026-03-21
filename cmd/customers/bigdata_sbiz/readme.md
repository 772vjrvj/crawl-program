1. "소상공인시장진흥공단"에서 "빅데이터 상권분석" > "간단분석" 에 들어간다. ("https://bigdata.sbiz.or.kr/#/hotplace/gis")

2. "상권분석 서울시 치과.xlsx" 에 있는 서울시 동단위 별로 "유동인구", "직장인구", "주거인구", "업소" 데이터를 가져와서 "상권분석 서울시 치과.xlsx"에 업데이트 한다. 

3. 치과수는 좌측 간단분석 섹션에서 보건의료 - 치과의원 클릭 후 업소 클릭하시면 개수가 나옵니다

방식

1. 서울시 동을 모두 가져와서 json으로 만든다. - 완료
2. 모든 동에 위도 경도를 붙여 json을 만든다. - 완료
3. 동단위와 위도 경도 가 있는 json 배열을 for문 돌면서 "유동인구", "직장인구", "주거인구", "업소"데이터를 가져온다.

https://bigdata.sbiz.or.kr/gis/api/getMapRadsStorCnt.json?mapLevel=3&substr=8&minXAxis=199096&maxXAxis=206768&minYAxis=442277&maxYAxis=445713&bzznType=1


업소
https://bigdata.sbiz.or.kr/gis/api/getMapRadsStorCnt.json?mapLevel=3&substr=8&minXAxis=199096&maxXAxis=206768&minYAxis=442277&maxYAxis=445713&bzznType=1
{"storeCnt":"14,048","yAxis":444602.139415712,"xAxis":203140.475880519,"admCd":"11680640","admNm":"역삼1동"}
"storeCnt":"14,048"

유동인구
https://bigdata.sbiz.or.kr/gis/api/getMapRadsPopCnt.json?mapLevel=3&substr=8&minXAxis=199096&maxXAxis=206768&minYAxis=442277&maxYAxis=445713&bzznType=1
{"yAxis":444602.105569838,"xAxis":203140.497075467,"popCnt":"631,408","ro":10,"admCd":"11680640","admNm":"역삼1동"}
"popCnt":"631,408"

직장인구
https://bigdata.sbiz.or.kr/gis/api/getMapRadsWrcpplCnt.json?mapLevel=3&substr=8&minXAxis=199096&maxXAxis=206768&minYAxis=442277&maxYAxis=445713&bzznType=1
{"yAxis":444602.105569838,"xAxis":203140.497075467,"wrcpplCnt":"258,274","ro":13,"admCd":"11680640","admNm":"역삼1동"}
"wrcpplCnt":"258,274"

주거인구
https://bigdata.sbiz.or.kr/gis/api/getMapRadsWholPpltnCnt.json?mapLevel=3&substr=8&minXAxis=199096&maxXAxis=206768&minYAxis=442277&maxYAxis=445713&bzznType=1
{"hhCnt":"23,884","yAxis":444602.105569838,"xAxis":203140.497075467,"wholPpltnCnt":"34,279","ro":10,"admCd":"11680640","admNm":"역삼1동"}
"wholPpltnCnt":"34,279"

치과수
https://bigdata.sbiz.or.kr/gis/api/getMapRadsStorCnt.json?mapLevel=3&substr=8&minXAxis=199096&maxXAxis=206768&minYAxis=442277&maxYAxis=445713&upjongCd=Q10210&bzznType=1
upjongCd
Q10210
{"storeCnt":"96","yAxis":444602.139415712,"xAxis":203140.475880519,"admCd":"11680640","admNm":"역삼1동"}
"storeCnt":"96"


4. 해당 데이터를 "상권분석 서울시 치과.xlsx"에 업데이트 한다.
