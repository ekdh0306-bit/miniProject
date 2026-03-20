import json

from LMS.domain.AnalysisResult import AnalysisResult
from LMS.domain.MediaFile import MediaFile

class MediaBoard:
   # ai객체탐지 전체목록을 출력하기 위한 데이터 객체
    def __init__(self, media: MediaFile, analysis:AnalysisResult,raw_date=""):
        self.media = media
        self.analysis = analysis
        self.raw_date = raw_date

    @classmethod
    def from_join(cls, row:dict):
        """JOIN 쿼리의 결과를 이용하여 두가지의 객체를 모두 불러온다"""
        if not row: return None
        media = MediaFile.from_db(row)
        analysis = AnalysisResult.from_db(row)
        upload_date = row.get('uploaded_at') or ""
        return cls(media, analysis, upload_date)


    def to_front_dict(self):

        front_status = 'done' if self.analysis.status == 'SUCCESS' else 'pending'
        res_json = self.analysis.result_json
        if isinstance(res_json, dict):

            safe_result = json.dumps(res_json, ensure_ascii=False)
        else:
            safe_result = str(res_json or "분석 중입니다.")


        safe_result = safe_result.replace("'", "\\'")
        return {
            "id": self.media.id,  # item.id 대응
            "analysis_id": getattr(self.analysis, 'id', None),  # item.analysis_id 대응
            "media_id": self.media.id,
            "file_type": self.media.file_type,
            "file_path": f"/uploads/{self.media.file_name}",  # 경로까지 완성하여 넘긴다
            "description": self.media.file_name,
            "created_at": str(self.raw_date)[:10] if self.raw_date else "",
            "status": front_status,
            "analysis_result": safe_result
        }