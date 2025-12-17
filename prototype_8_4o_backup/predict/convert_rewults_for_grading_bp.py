import os
import pandas as pd
from tqdm import tqdm
all_results = os.listdir('../2_extraction/사업방법서_추출결과_qwen25_try2/')

for folder in tqdm(all_results):
    if not os.path.isdir(os.path.join('../2_extraction/사업방법서_추출결과_qwen25_try2/', folder)):
        continue
    folder_files = os.listdir(os.path.join('../2_extraction/사업방법서_추출결과_qwen25_try2/', folder))
    
    eligibility_results = None
    ineligibility_results = None
    
    for file in folder_files:
        if '_6_eligibility_final' in file:
            results = pd.read_excel(os.path.join('../2_extraction/사업방법서_추출결과_qwen25_try2/', folder, file))
            drop_cols = ['주피보험자최소가입연령', '주피보험자최대가입연령', '주피보험자최소가입연령구분코드', '주피보험자최대가입연령구분코드', '주피보험자가입성별']
            df = results.drop(drop_cols, axis=1).drop_duplicates().reset_index(drop = True).fillna('')

            group_cols = [col for col in df.columns if col not in ['보험기간','납입기간']]
            eligibility_results = df.groupby(group_cols, sort=False).agg({
                '보험기간': lambda x: '/'.join(map(str, x.unique())),
                '납입기간': lambda x: '/'.join(map(str, x.unique()))
            }).reset_index()
            
        if '_6_ineligibility_final' in file:
            results = pd.read_excel(os.path.join('../2_extraction/사업방법서_추출결과_qwen25_try2/', folder, file))
            drop_cols = ['주피보험자최소가입연령', '주피보험자최대가입연령', '주피보험자최소가입연령구분코드', '주피보험자최대가입연령구분코드', '주피보험자가입성별']
            df = results.drop(drop_cols, axis=1).drop_duplicates().reset_index(drop = True).fillna('')

            group_cols = [col for col in df.columns if col not in ['납입기간']]
            ineligibility_results = df.groupby(group_cols, sort=False).agg({
                '납입기간': lambda x: '/'.join(map(str, x.unique()))}).reset_index()
    
    # 하나의 엑셀 파일에 두 시트로 저장
    if eligibility_results is not None or ineligibility_results is not None:
        os.makedirs(os.path.join('../2_extraction/사업방법서_추출결과_qwen25_try2_검수'), exist_ok=True)
        
        with pd.ExcelWriter(os.path.join('../2_extraction/사업방법서_추출결과_qwen25_try2_검수', f'{folder}.xlsx')) as writer:
            if eligibility_results is not None:
                eligibility_results.to_excel(writer, sheet_name='가입가능조건', index=False)
            if ineligibility_results is not None:
                ineligibility_results.to_excel(writer, sheet_name='가입불가조건', index=False)