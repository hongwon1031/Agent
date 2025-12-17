import pandas as pd
import os
import glob
from tqdm import tqdm
from collections import defaultdict
import numpy as np
from typing import Dict, List, Tuple, Set

class BusinessMethodEvaluation:
    def __init__(self, qwen3_folder: str, answer_folder: str):
        """
        사업방법서 추출 결과 채점 클래스
        
        Args:
            qwen3_folder: Qwen3 추출 결과 폴더 경로
            answer_folder: 정답지 폴더 경로
        """
        self.qwen3_folder = qwen3_folder
        self.answer_folder = answer_folder
        
        # 칼럼 그룹 정의
        self.column_groups = {
            '보종명': ['보종명'],
            '유형': ['유형1', '유형2', '유형3', '유형4', '유형5'],  # 유형1~유형n을 합쳐서 처리
            '보험기간': ['보험기간'],
            '납입기간': ['납입기간']
        }
    
    def get_matching_files(self) -> List[Tuple[str, str]]:
        """
        두 폴더에서 동일한 파일명을 가진 파일들을 찾아서 반환
        
        Returns:
            List[Tuple[str, str]]: (qwen3_file_path, answer_file_path) 튜플 리스트
        """
        qwen3_files = glob.glob(os.path.join(self.qwen3_folder, "*.xlsx"))
        answer_files = glob.glob(os.path.join(self.answer_folder, "*.xlsx"))
        
        # 파일명만 추출 (확장자 제외)
        qwen3_filenames = {os.path.splitext(os.path.basename(f))[0]: f for f in qwen3_files}
        answer_filenames = {os.path.splitext(os.path.basename(f))[0]: f for f in answer_files}
        
        # 공통 파일명 찾기
        common_filenames = set(qwen3_filenames.keys()) & set(answer_filenames.keys())
        
        matching_files = []
        for filename in common_filenames:
            matching_files.append((qwen3_filenames[filename], answer_filenames[filename]))
        
        return matching_files
    
    def get_all_answer_files(self) -> List[str]:
        """
        정답지 폴더의 모든 파일을 반환
        
        Returns:
            List[str]: 정답지 파일 경로 리스트
        """
        answer_files = glob.glob(os.path.join(self.answer_folder, "*.xlsx"))
        return answer_files
    
    def get_missing_files(self) -> List[str]:
        """
        정답지에는 있지만 추출 결과 파일이 없는 파일들을 찾아서 반환
        
        Returns:
            List[str]: 누락된 파일 경로 리스트
        """
        qwen3_files = glob.glob(os.path.join(self.qwen3_folder, "*.xlsx"))
        answer_files = glob.glob(os.path.join(self.answer_folder, "*.xlsx"))
        
        # 파일명만 추출 (확장자 제외)
        qwen3_filenames = {os.path.splitext(os.path.basename(f))[0]: f for f in qwen3_files}
        answer_filenames = {os.path.splitext(os.path.basename(f))[0]: f for f in answer_files}
        
        # 정답지에는 있지만 추출 결과 파일이 없는 파일들
        missing_filenames = set(answer_filenames.keys()) - set(qwen3_filenames.keys())
        
        missing_files = []
        for filename in missing_filenames:
            missing_files.append(answer_filenames[filename])
        
        return missing_files
    
    def evaluate_missing_files(self) -> List[Dict]:
        """
        정답지에는 있지만 추출 결과 파일이 없는 파일들을 오답으로 처리
        
        Returns:
            List[Dict]: 누락된 파일들의 오답 결과
        """
        missing_files = self.get_missing_files()
        missing_results = []
        
        for answer_file in missing_files:
            # 가입가능조건 시트 평가
            answer_joinable_df = self.load_excel_sheet(answer_file, "가입가능조건")
            if not answer_joinable_df.empty:
                result = {
                    'filename': os.path.basename(answer_file),
                    'sheet_name': '가입가능조건',
                    'condition_type': '가입가능조건',
                    'row_comparison': {
                        'total_rows': len(answer_joinable_df),
                        'correct_rows': 0,
                        'incorrect_rows': len(answer_joinable_df),
                        'row_accuracy': 0.0,
                        'row_f1_score': 0.0,
                        'precision': 0.0,
                        'recall': 0.0
                    },
                    'column_performance': {},
                    'total_rows': len(answer_joinable_df),
                    'correct_rows': 0,
                    'row_f1_score': 0.0,
                    'is_document_correct': False,
                    'status': 'missing_file'  # 누락된 파일임을 표시
                }
                missing_results.append(result)
            
            # 가입불가조건 시트 평가
            answer_impossible_df = self.load_excel_sheet(answer_file, "가입불가조건")
            if not answer_impossible_df.empty:
                result = {
                    'filename': os.path.basename(answer_file),
                    'sheet_name': '가입불가조건',
                    'condition_type': '가입불가조건',
                    'row_comparison': {
                        'total_rows': len(answer_impossible_df),
                        'correct_rows': 0,
                        'incorrect_rows': len(answer_impossible_df),
                        'row_accuracy': 0.0,
                        'row_f1_score': 0.0,
                        'precision': 0.0,
                        'recall': 0.0
                    },
                    'column_performance': {},
                    'total_rows': len(answer_impossible_df),
                    'correct_rows': 0,
                    'row_f1_score': 0.0,
                    'is_document_correct': False,
                    'status': 'missing_file'  # 누락된 파일임을 표시
                }
                missing_results.append(result)
        
        return missing_results
    
    def load_excel_sheet(self, file_path: str, sheet_name: str) -> pd.DataFrame:
        """
        Excel 파일의 특정 시트를 로드하여 DataFrame으로 반환
        
        Args:
            file_path: Excel 파일 경로
            sheet_name: 시트명
            
        Returns:
            pd.DataFrame: 로드된 데이터
        """
        try:
            # 시트가 존재하는지 확인
            excel_file = pd.ExcelFile(file_path)
            if sheet_name not in excel_file.sheet_names:
                return pd.DataFrame()
            
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            # NaN 값을 빈 문자열로 변환
            df = df.fillna('')
            return df
        except Exception as e:
            print(f"시트 로드 오류 {file_path} - {sheet_name}: {e}")
            return pd.DataFrame()
    
    def normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        DataFrame을 정규화 (공백 제거, 소문자 변환 등)
        
        Args:
            df: 원본 DataFrame
            
        Returns:
            pd.DataFrame: 정규화된 DataFrame
        """
        if df.empty:
            return df
        
        # 모든 문자열 컬럼에 대해 공백 제거 및 정규화
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        return df
    
    def compare_rows(self, qwen3_df: pd.DataFrame, answer_df: pd.DataFrame) -> Dict:
        """
        두 DataFrame의 행을 비교하여 결과 반환
        
        Args:
            qwen3_df: Qwen3 추출 결과 DataFrame
            answer_df: 정답지 DataFrame
            
        Returns:
            Dict: 비교 결과
        """
        if qwen3_df.empty or answer_df.empty:
            return {
                'total_rows': 0,
                'correct_rows': 0,
                'incorrect_rows': 0,
                'row_accuracy': 0.0,
                'row_f1_score': 0.0
            }
        
        # 각 행을 문자열로 변환하여 set으로 만들기
        qwen3_rows = set()
        answer_rows = set()
        
        for _, row in qwen3_df.iterrows():
            row_str = '|'.join([str(val).strip() for val in row.values])
            if row_str.strip():  # 빈 행 제외
                qwen3_rows.add(row_str)
        
        for _, row in answer_df.iterrows():
            row_str = '|'.join([str(val).strip() for val in row.values])
            if row_str.strip():  # 빈 행 제외
                answer_rows.add(row_str)
        
        # 정확한 행 수 계산
        correct_rows = len(qwen3_rows & answer_rows)
        total_rows = len(answer_rows)
        incorrect_rows = total_rows - correct_rows
        
        # 정확도 및 F1 점수 계산
        precision = correct_rows / len(qwen3_rows) if len(qwen3_rows) > 0 else 0
        recall = correct_rows / total_rows if total_rows > 0 else 0
        row_f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            'total_rows': total_rows,
            'correct_rows': correct_rows,
            'incorrect_rows': incorrect_rows,
            'row_accuracy': correct_rows / total_rows if total_rows > 0 else 0,
            'row_f1_score': row_f1_score,
            'precision': precision,
            'recall': recall
        }
    
    def calculate_column_performance(self, qwen3_df: pd.DataFrame, answer_df: pd.DataFrame) -> Dict:
        """
        칼럼별 성능 계산
        
        Args:
            qwen3_df: Qwen3 추출 결과 DataFrame
            answer_df: 정답지 DataFrame
            
        Returns:
            Dict: 칼럼별 성능 결과
        """
        column_results = {}
        
        for group_name, columns in self.column_groups.items():
            group_results = {}
            
            for col in columns:
                if col in qwen3_df.columns and col in answer_df.columns:
                    # 해당 칼럼의 값들을 set으로 변환
                    qwen3_values = set(qwen3_df[col].astype(str).str.strip())
                    answer_values = set(answer_df[col].astype(str).str.strip())
                    
                    # 빈 값 제거
                    qwen3_values.discard('')
                    qwen3_values.discard('nan')
                    answer_values.discard('')
                    answer_values.discard('nan')
                    
                    if len(answer_values) > 0:
                        correct_values = len(qwen3_values & answer_values)
                        precision = correct_values / len(qwen3_values) if len(qwen3_values) > 0 else 0
                        recall = correct_values / len(answer_values) if len(answer_values) > 0 else 0
                        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
                        
                        group_results[col] = {
                            'precision': precision,
                            'recall': recall,
                            'f1_score': f1_score,
                            'correct_values': correct_values,
                            'total_answer_values': len(answer_values)
                        }
                    else:
                        group_results[col] = {
                            'precision': 0.0,
                            'recall': 0.0,
                            'f1_score': 0.0,
                            'correct_values': 0,
                            'total_answer_values': 0
                        }
            
            # 그룹별 평균 성능 계산
            if group_results:
                avg_precision = np.mean([v['precision'] for v in group_results.values()])
                avg_recall = np.mean([v['recall'] for v in group_results.values()])
                avg_f1 = np.mean([v['f1_score'] for v in group_results.values()])
                
                column_results[group_name] = {
                    'columns': group_results,
                    'avg_precision': avg_precision,
                    'avg_recall': avg_recall,
                    'avg_f1_score': avg_f1
                }
        
        return column_results
    
    def evaluate_file_sheets(self, qwen3_file: str, answer_file: str) -> List[Dict]:
        """
        단일 파일의 각 시트에 대한 평가 수행
        
        Args:
            qwen3_file: Qwen3 추출 결과 파일 경로
            answer_file: 정답지 파일 경로
            
        Returns:
            List[Dict]: 각 시트별 평가 결과
        """
        results = []
        
        # 가입가능조건 시트 평가 (항상 존재)
        qwen3_joinable_df = self.load_excel_sheet(qwen3_file, "가입가능조건")
        answer_joinable_df = self.load_excel_sheet(answer_file, "가입가능조건")
        
        if not answer_joinable_df.empty:
            # 데이터 정규화
            qwen3_joinable_df = self.normalize_dataframe(qwen3_joinable_df)
            answer_joinable_df = self.normalize_dataframe(answer_joinable_df)
            
            # 행 비교
            row_comparison = self.compare_rows(qwen3_joinable_df, answer_joinable_df)
            
            # 칼럼별 성능
            column_performance = self.calculate_column_performance(qwen3_joinable_df, answer_joinable_df)
            
            # 문서 정답 여부 (모든 행이 정확하면 정답)
            is_document_correct = row_comparison['row_f1_score'] == 1.0
            
            result = {
                'filename': os.path.basename(qwen3_file),
                'sheet_name': '가입가능조건',
                'condition_type': '가입가능조건',
                'row_comparison': row_comparison,
                'column_performance': column_performance,
                'total_rows': row_comparison['total_rows'],
                'correct_rows': row_comparison['correct_rows'],
                'row_f1_score': row_comparison['row_f1_score'],
                'is_document_correct': is_document_correct
            }
            results.append(result)
        
        # 가입불가조건 시트 평가 (선택적 존재)
        qwen3_impossible_df = self.load_excel_sheet(qwen3_file, "가입불가조건")
        answer_impossible_df = self.load_excel_sheet(answer_file, "가입불가조건")
        
        if not answer_impossible_df.empty:
            # 데이터 정규화
            qwen3_impossible_df = self.normalize_dataframe(qwen3_impossible_df)
            answer_impossible_df = self.normalize_dataframe(answer_impossible_df)
            
            # 행 비교
            row_comparison = self.compare_rows(qwen3_impossible_df, answer_impossible_df)
            
            # 칼럼별 성능
            column_performance = self.calculate_column_performance(qwen3_impossible_df, answer_impossible_df)
            
            # 문서 정답 여부 (모든 행이 정확하면 정답)
            is_document_correct = row_comparison['row_f1_score'] == 1.0
            
            result = {
                'filename': os.path.basename(qwen3_file),
                'sheet_name': '가입불가조건',
                'condition_type': '가입불가조건',
                'row_comparison': row_comparison,
                'column_performance': column_performance,
                'total_rows': row_comparison['total_rows'],
                'correct_rows': row_comparison['correct_rows'],
                'row_f1_score': row_comparison['row_f1_score'],
                'is_document_correct': is_document_correct
            }
            results.append(result)
        
        return results
    
    def evaluate_all_files(self) -> Dict:
        """
        모든 매칭 파일에 대한 평가 수행 (누락된 파일도 오답으로 처리)
        
        Returns:
            Dict: 전체 평가 결과
        """
        matching_files = self.get_matching_files()
        print(f"총 {len(matching_files)}개의 매칭 파일을 찾았습니다.")
        
        # 매칭되는 파일들 평가
        all_results = []
        condition_results = defaultdict(list)
        
        for qwen3_file, answer_file in tqdm(matching_files, desc="매칭 파일 평가"):
            sheet_results = self.evaluate_file_sheets(qwen3_file, answer_file)
            for result in sheet_results:
                result['status'] = 'matched'  # 매칭된 파일임을 표시
                all_results.append(result)
                condition_results[result['condition_type']].append(result)
        
        # 누락된 파일들 평가 (오답으로 처리)
        missing_results = self.evaluate_missing_files()
        print(f"총 {len(missing_results)}개의 누락된 파일을 오답으로 처리합니다.")
        
        for result in missing_results:
            all_results.append(result)
            condition_results[result['condition_type']].append(result)
        
        # 전체 통계 계산
        total_stats = self.calculate_total_statistics(all_results)
        condition_stats = self.calculate_condition_statistics(condition_results)
        
        return {
            'total_answer_files': len(self.get_all_answer_files()),
            'total_matched_files': len(matching_files),
            'total_missing_files': len(self.get_missing_files()),
            'total_sheets': len(all_results),
            'total_statistics': total_stats,
            'condition_statistics': condition_stats,
            'sheet_results': all_results
        }
    
    def calculate_total_statistics(self, results: List[Dict]) -> Dict:
        """
        전체 통계 계산
        
        Args:
            results: 모든 시트의 평가 결과
            
        Returns:
            Dict: 전체 통계
        """
        if not results:
            return {}
        
        total_rows = sum(r['total_rows'] for r in results)
        total_correct_rows = sum(r['correct_rows'] for r in results)
        
        # 문서 기준 성능 (시트 단위)
        document_accuracy = len([r for r in results if r['is_document_correct']]) / len(results)
        
        # Row 기준 F1 점수
        avg_row_f1 = np.mean([r['row_f1_score'] for r in results])
        
        return {
            'total_rows': total_rows,
            'total_correct_rows': total_correct_rows,
            'overall_row_accuracy': total_correct_rows / total_rows if total_rows > 0 else 0,
            'document_accuracy': document_accuracy,
            'avg_row_f1_score': avg_row_f1
        }
    
    def calculate_condition_statistics(self, condition_results: Dict) -> Dict:
        """
        조건별 통계 계산
        
        Args:
            condition_results: 조건별 결과
            
        Returns:
            Dict: 조건별 통계
        """
        stats = {}
        
        for condition_type, results in condition_results.items():
            if not results:
                continue
            
            total_rows = sum(r['total_rows'] for r in results)
            total_correct_rows = sum(r['correct_rows'] for r in results)
            
            # 문서 기준 성능
            document_accuracy = len([r for r in results if r['is_document_correct']]) / len(results)
            
            # Row 기준 F1 점수
            avg_row_f1 = np.mean([r['row_f1_score'] for r in results])
            
            # 칼럼별 평균 F1 점수
            column_f1_scores = defaultdict(list)
            for result in results:
                for group_name, group_data in result['column_performance'].items():
                    column_f1_scores[group_name].append(group_data['avg_f1_score'])
            
            avg_column_f1 = {}
            for group_name, scores in column_f1_scores.items():
                avg_column_f1[group_name] = np.mean(scores)
            
            stats[condition_type] = {
                'sheet_count': len(results),
                'total_rows': total_rows,
                'total_correct_rows': total_correct_rows,
                'row_accuracy': total_correct_rows / total_rows if total_rows > 0 else 0,
                'document_accuracy': document_accuracy,
                'avg_row_f1_score': avg_row_f1,
                'avg_column_f1_scores': avg_column_f1
            }
        
        return stats
    
    def print_results(self, results: Dict):
        """
        결과 출력
        
        Args:
            results: 평가 결과
        """
        print("\n" + "="*80)
        print("사업방법서 추출 결과 채점 결과")
        print("="*80)
        
        print(f"\n전체 정답지 파일 수: {results['total_answer_files']}")
        print(f"매칭된 파일 수: {results['total_matched_files']}")
        print(f"누락된 파일 수: {results['total_missing_files']}")
        print(f"전체 시트 수: {results['total_sheets']}")
        
        # 전체 통계
        total_stats = results['total_statistics']
        print(f"\n[전체 통계]")
        print(f"  - 총 행 수: {total_stats['total_rows']:,}")
        print(f"  - 정답 행 수: {total_stats['total_correct_rows']:,}")
        print(f"  - 전체 행 정확도: {total_stats['overall_row_accuracy']:.4f}")
        print(f"  - 문서 기준 정확도: {total_stats['document_accuracy']:.4f}")
        print(f"  - 평균 Row F1 점수: {total_stats['avg_row_f1_score']:.4f}")
        
        # 조건별 통계
        print(f"\n[조건별 통계]")
        for condition_type, stats in results['condition_statistics'].items():
            print(f"\n{condition_type}:")
            print(f"  - 시트 수: {stats['sheet_count']}")
            print(f"  - 총 행 수: {stats['total_rows']:,}")
            print(f"  - 행 정확도: {stats['row_accuracy']:.4f}")
            print(f"  - 문서 정확도: {stats['document_accuracy']:.4f}")
            print(f"  - 평균 Row F1 점수: {stats['avg_row_f1_score']:.4f}")
            
            print(f"  - 칼럼별 평균 F1 점수:")
            for col_name, f1_score in stats['avg_column_f1_scores'].items():
                print(f"    * {col_name}: {f1_score:.4f}")

def main():
    # 폴더 경로 설정
    qwen3_folder = "사업방법서_추출결과_qwen25_try2_검수"
    answer_folder = "사업방법서_정답지"
    
    # 평가 실행
    evaluator = BusinessMethodEvaluation(qwen3_folder, answer_folder)
    results = evaluator.evaluate_all_files()
    
    # 결과 출력
    evaluator.print_results(results)
    
    # 결과를 Excel 파일로 저장
    save_results_to_excel(results, "evaluation_results.xlsx")

def evaluate_dataframes(qwen3_df: pd.DataFrame, answer_df: pd.DataFrame, filename: str = None) -> Dict:
    """
    두 DataFrame을 직접 비교하여 평가 결과를 반환 (notebook용)
    
    Args:
        qwen3_df: Qwen3 추출 결과 DataFrame
        answer_df: 정답지 DataFrame
        filename: 파일명 (선택사항, 결과에 포함)
        
    Returns:
        Dict: 평가 결과
    """
    # 데이터 정규화
    qwen3_df = qwen3_df.copy()
    answer_df = answer_df.copy()
    
    # NaN 값을 빈 문자열로 변환
    qwen3_df = qwen3_df.fillna('')
    answer_df = answer_df.fillna('')
    
    # 모든 문자열 컬럼에 대해 공백 제거
    for col in qwen3_df.columns:
        if qwen3_df[col].dtype == 'object':
            qwen3_df[col] = qwen3_df[col].astype(str).str.strip()
    
    for col in answer_df.columns:
        if answer_df[col].dtype == 'object':
            answer_df[col] = answer_df[col].astype(str).str.strip()
    
    # 행 비교
    row_comparison = compare_rows_direct(qwen3_df, answer_df)
    
    # 칼럼별 성능
    column_performance = calculate_column_performance_direct(qwen3_df, answer_df)
    
    # 문서 정답 여부 (모든 행이 정확하면 정답)
    is_document_correct = row_comparison['row_f1_score'] == 1.0
    
    result = {
        'filename': filename or 'unknown',
        'row_comparison': row_comparison,
        'column_performance': column_performance,
        'total_rows': row_comparison['total_rows'],
        'correct_rows': row_comparison['correct_rows'],
        'row_f1_score': row_comparison['row_f1_score'],
        'is_document_correct': is_document_correct
    }
    
    return result

def compare_rows_direct(qwen3_df: pd.DataFrame, answer_df: pd.DataFrame) -> Dict:
    """
    두 DataFrame의 행을 직접 비교하여 결과 반환
    
    Args:
        qwen3_df: Qwen3 추출 결과 DataFrame
        answer_df: 정답지 DataFrame
        
    Returns:
        Dict: 비교 결과
    """
    if qwen3_df.empty or answer_df.empty:
        return {
            'total_rows': 0,
            'correct_rows': 0,
            'incorrect_rows': 0,
            'row_accuracy': 0.0,
            'row_f1_score': 0.0,
            'precision': 0.0,
            'recall': 0.0
        }
    
    # 각 행을 문자열로 변환하여 set으로 만들기
    qwen3_rows = set()
    answer_rows = set()
    
    for _, row in qwen3_df.iterrows():
        row_str = '|'.join([str(val).strip() for val in row.values])
        if row_str.strip():  # 빈 행 제외
            qwen3_rows.add(row_str)
    
    for _, row in answer_df.iterrows():
        row_str = '|'.join([str(val).strip() for val in row.values])
        if row_str.strip():  # 빈 행 제외
            answer_rows.add(row_str)
    
    # 정확한 행 수 계산
    correct_rows = len(qwen3_rows & answer_rows)
    total_rows = len(answer_rows)
    incorrect_rows = total_rows - correct_rows
    
    # 정확도 및 F1 점수 계산
    precision = correct_rows / len(qwen3_df) if len(qwen3_df) > 0 else 0
    recall = correct_rows / total_rows if total_rows > 0 else 0
    row_f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        'total_rows': total_rows,
        'correct_rows': correct_rows,
        'incorrect_rows': incorrect_rows,
        'row_accuracy': correct_rows / total_rows if total_rows > 0 else 0,
        'row_f1_score': row_f1_score,
        'precision': precision,
        'recall': recall
    }

def calculate_column_performance_direct(qwen3_df: pd.DataFrame, answer_df: pd.DataFrame) -> Dict:
    """
    두 DataFrame의 칼럼별 성능을 직접 계산
    
    Args:
        qwen3_df: Qwen3 추출 결과 DataFrame
        answer_df: 정답지 DataFrame
        
    Returns:
        Dict: 칼럼별 성능 결과
    """
    # 칼럼 그룹 정의
    column_groups = {
        '보종명': ['보종명'],
        '유형': ['유형1', '유형2', '유형3', '유형4', '유형5'],
        '보험기간': ['보험기간'],
        '납입기간': ['납입기간']
    }
    
    column_results = {}
    
    for group_name, columns in column_groups.items():
        group_results = {}
        
        for col in columns:
            if col in qwen3_df.columns and col in answer_df.columns:
                # 해당 칼럼의 값들을 set으로 변환
                qwen3_values = set(qwen3_df[col].astype(str).str.strip())
                answer_values = set(answer_df[col].astype(str).str.strip())
                
                # 빈 값 제거
                qwen3_values.discard('')
                qwen3_values.discard('nan')
                answer_values.discard('')
                answer_values.discard('nan')
                
                if len(answer_values) > 0:
                    correct_values = len(qwen3_values & answer_values)
                    precision = correct_values / len(qwen3_values) if len(qwen3_values) > 0 else 0
                    recall = correct_values / len(answer_values) if len(answer_values) > 0 else 0
                    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
                    
                    group_results[col] = {
                        'precision': precision,
                        'recall': recall,
                        'f1_score': f1_score,
                        'correct_values': correct_values,
                        'total_answer_values': len(answer_values)
                    }
                else:
                    group_results[col] = {
                        'precision': 0.0,
                        'recall': 0.0,
                        'f1_score': 0.0,
                        'correct_values': 0,
                        'total_answer_values': 0
                    }
        
        # 그룹별 평균 성능 계산
        if group_results:
            avg_precision = np.mean([v['precision'] for v in group_results.values()])
            avg_recall = np.mean([v['recall'] for v in group_results.values()])
            avg_f1 = np.mean([v['f1_score'] for v in group_results.values()])
            
            column_results[group_name] = {
                'columns': group_results,
                'avg_precision': avg_precision,
                'avg_recall': avg_recall,
                'avg_f1_score': avg_f1
            }
    
    return column_results

def print_dataframe_evaluation(result: Dict):
    """
    DataFrame 평가 결과를 출력
    
    Args:
        result: evaluate_dataframes 함수의 결과
    """
    print("="*60)
    print(f"DataFrame 평가 결과 - {result['filename']}")
    print("="*60)
    
    # 행 비교 결과
    row_comp = result['row_comparison']
    print(f"\n[행 비교 결과]")
    print(f"  - 총 행 수: {row_comp['total_rows']}")
    print(f"  - 정답 행 수: {row_comp['correct_rows']}")
    print(f"  - 오답 행 수: {row_comp['incorrect_rows']}")
    print(f"  - 행 정확도: {row_comp['row_accuracy']:.4f}")
    print(f"  - Row F1 점수: {row_comp['row_f1_score']:.4f}")
    print(f"  - Precision: {row_comp['precision']:.4f}")
    print(f"  - Recall: {row_comp['recall']:.4f}")
    print(f"  - 문서 정답 여부: {'예' if result['is_document_correct'] else '아니오'}")
    
    # 칼럼별 성능
    print(f"\n[칼럼별 성능]")
    for group_name, group_data in result['column_performance'].items():
        print(f"\n  {group_name}:")
        print(f"    - 평균 Precision: {group_data['avg_precision']:.4f}")
        print(f"    - 평균 Recall: {group_data['avg_recall']:.4f}")
        print(f"    - 평균 F1 점수: {group_data['avg_f1_score']:.4f}")
        
        # 개별 칼럼 성능
        for col_name, col_data in group_data['columns'].items():
            print(f"      * {col_name}: F1={col_data['f1_score']:.4f}")

def save_results_to_excel(results: Dict, filename: str):
    """
    결과를 Excel 파일로 저장
    
    Args:
        results: 평가 결과
        filename: 저장할 파일명
    """
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # 전체 통계와 조건별 통계를 하나의 시트에 통합
        combined_stats_data = []
        
        # 전체 통계 추가
        total_stats = results['total_statistics']
        combined_stats_data.append({
            '구분': '전체',
            '파일수': results['total_answer_files'],
            '매칭파일수': results['total_matched_files'],
            '누락파일수': results['total_missing_files'],
            '시트수': results['total_sheets'],
            '총행수': total_stats['total_rows'],
            '정답행수': total_stats['total_correct_rows'],
            '행정확도': f"{total_stats['overall_row_accuracy']:.4f}",
            '문서정확도': f"{total_stats['document_accuracy']:.4f}",
            '평균Row_F1점수': f"{total_stats['avg_row_f1_score']:.4f}",
            '보종명_F1': '-',  # 전체에서는 칼럼별 F1 점수 계산 불가
            '유형_F1': '-',
            '보험기간_F1': '-',
            '납입기간_F1': '-',
            '모수': results['total_answer_files'],  # 전체 정답지 파일 수
            '정답개수': results['total_matched_files']  # 매칭된 파일 수
        })
        
        # 조건별 통계 추가
        for condition_type, stats in results['condition_statistics'].items():
            # 칼럼별 평균 F1 점수 계산
            column_f1_scores = stats.get('avg_column_f1_scores', {})
            
            # 해당 조건의 누락된 파일 수 계산 (정답지 기준)
            missing_files_for_condition = len([r for r in results['sheet_results'] 
                                            if r['condition_type'] == condition_type and r.get('status') == 'missing_file'])
            
            combined_stats_data.append({
                '구분': condition_type,
                '파일수': stats['sheet_count'],
                '매칭파일수': stats['sheet_count'] - missing_files_for_condition,  # 전체 시트 수에서 누락된 시트 수를 뺌
                '누락파일수': missing_files_for_condition,  # 해당 조건의 누락된 시트 수
                '시트수': stats['sheet_count'],
                '총행수': stats['total_rows'],
                '정답행수': stats['total_correct_rows'],
                '행정확도': f"{stats['row_accuracy']:.4f}",
                '문서정확도': f"{stats['document_accuracy']:.4f}",
                '평균Row_F1점수': f"{stats['avg_row_f1_score']:.4f}",
                '보종명_F1': f"{column_f1_scores.get('보종명', 0):.2f}",
                '유형_F1': f"{column_f1_scores.get('유형', 0):.2f}",
                '보험기간_F1': f"{column_f1_scores.get('보험기간', 0):.2f}",
                '납입기간_F1': f"{column_f1_scores.get('납입기간', 0):.2f}",
                '모수': stats['sheet_count'],  # 해당 조건의 시트 수
                '정답개수': len([r for r in results['sheet_results'] if r['condition_type'] == condition_type and r['is_document_correct']])
            })
        
        # 통합 통계 시트 생성
        combined_stats_df = pd.DataFrame(combined_stats_data)
        combined_stats_df.to_excel(writer, sheet_name='통합통계', index=False)
        
        # 시트별 상세 결과
        sheet_data = []
        for result in results['sheet_results']:
            row_data = {
                '파일명': result['filename'],
                '시트명': result['sheet_name'],
                '조건유형': result['condition_type'],
                '총행수': result['total_rows'],
                '정답행수': result['correct_rows'],
                '행정확도': result['row_comparison']['row_accuracy'],
                'Row_F1점수': result['row_f1_score'],
                '문서정답여부': '예' if result['is_document_correct'] else '아니오',
                '상태': result.get('status', 'unknown')  # matched 또는 missing_file
            }
            sheet_data.append(row_data)
        
        if sheet_data:
            sheet_df = pd.DataFrame(sheet_data)
            sheet_df.to_excel(writer, sheet_name='시트별결과', index=False)
    
    print(f"\n결과가 {filename} 파일로 저장되었습니다.")

if __name__ == "__main__":
    main()