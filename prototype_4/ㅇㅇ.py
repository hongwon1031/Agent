extracted_data = {
    "header": [
              "명칭",
              "보험종목",
              "보험종목_1",
              "보장계약"
            ],
            "data": [
              [
                "통합암(전이포함)진단특약TC\n(무배당, 해약환급금 미지급형)",
                "해약환급금\n미지급형",
                "간편심사(315)형\n/간편심사(335)형\n/간편심사(355)형\n/일반심사형",
                "두경부암(전이포함),\n위암 및 식도암(전이포함),\n소장·대장·항문암 및 기타암(전이포함),\n간·담낭·담도암 및 췌장암(전이포함),\n폐암(전이포함),\n흉곽내기관·중피성암 및 연조직암(전이포함),\n골·피부 등 전신부위암(전이포함),\n유방·비뇨기관·부신암 및 내분비선암(전이포함),\n남성/여성생식기암(전이포함),\n뇌암 및 중추신경계통암(전이포함),\n혈액암(전이포함)"
              ],
              [
                "통합암(전이포함)진단특약TC\n(무배당)",
                "일반형",
                "간편심사(315)형\n/간편심사(335)형\n/간편심사(355)형\n/일반심사형",
                "두경부암(전이포함),\n위암 및 식도암(전이포함),\n소장·대장·항문암 및 기타암(전이포함),\n간·담낭·담도암 및 췌장암(전이포함),\n폐암(전이포함),\n흉곽내기관·중피성암 및 연조직암(전이포함),\n골·피부 등 전신부위암(전이포함),\n유방·비뇨기관·부신암 및 내분비선암(전이포함),\n남성/여성생식기암(전이포함),\n뇌암 및 중추신경계통암(전이포함),\n혈액암(전이포함)"
              ]
            ]
        }
header = extracted_data['header']
data = extracted_data['data']


expected_per_row = []
for row in data:
    row_combos = 1
    for cell in row:
        cell_clean = cell.replace('\n', '').strip()
        values = [v.strip() for v in cell_clean.split('/') if v.strip()]
        print(f'✅values = {values}')
        print(f'✅Len_values = {len(values)}')
        row_combos *= len(values)
        print(f'❗row_combos = {row_combos}')
    expected_per_row.append(row_combos)

expected_total = sum(expected_per_row)
print(expected_total)