class MediaFile():
    def __init__(self, id, member_id, file_name, stored_path, file_type, uploaded_at):
        self.id = id
        self.member_id = member_id
        self.file_name = file_name
        self.stored_path = stored_path
        self.file_type = file_type # image or video
        self.uploaded_at = uploaded_at

    @classmethod
    def from_db(cls, row: dict):
        if row is None:
            return None
        return cls(
            id = row.get("id"),
            member_id = row.get("member_id"),
            file_name = row.get("file_name"),
            stored_path = row.get("stored_path"),
            file_type = row.get("file_type"),
            uploaded_at = row.get("uploaded_at")
        )