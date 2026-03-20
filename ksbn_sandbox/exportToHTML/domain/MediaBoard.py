from domain.AnalysisResult import AnalysisResult
from domain.MediaFile import MediaFile

class MediaBoard:
   # ai객체탐지 전체목록을 출력하기 위한 데이터 객체
    def __init__(self, media: MediaFile, analysis:AnalysisResult):
        self.media = media
        self.analysis = analysis

    @classmethod
    def from_join(cls, row:dict):
        """JOIN 쿼리의 결과를 이용하여 두가지의 객체를 모두 불러온다"""
        if not row: return None
        media = MediaFile.from_db(row)
        analysis = AnalysisResult.from_db(row)
        return cls(media, analysis)