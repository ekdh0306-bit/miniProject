-- (1) members: 사용자 정보 [cite: 6]
CREATE TABLE members (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    uid varchar(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role enum("user","admin","manager") default "user",
    active tinyint(1) DEFAULT '1',
    email varchar(200) NOT NULL,
    profile_imageboards varchar(255),
    bio varchar(255),
    CONSTRAINT chk_email_at CHECK (email LIKE '%@%')
);


-- (2) media_files: 이미지 정보 (게시글 역할 통합) 
CREATE TABLE media_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,           -- 업로드한 유저 [cite: 6]
    file_name VARCHAR(255) NOT NULL,  -- 화면 표시용 원본 파일명 
    stored_path VARCHAR(500) NOT NULL, -- AI가 분석할 서버 내 실제 경로 
    file_type ENUM('IMAGE', 'VIDEO') NOT NULL, -- 
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 
    memo varchar(50),
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE -- [cite: 7]
);


-- (3) analysis_results: AI 분석 결과 [cite: 3]
CREATE TABLE analysis_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    media_id INT NOT NULL,             -- 어떤 이미지의 결과인지 [cite: 3]
    status ENUM('PENDING', 'SUCCESS', 'FAIL') DEFAULT 'PENDING', -- 상태 제어 [cite: 3, 4]
    result_json JSON,                  -- AI 탐지 좌표 및 태그 정보 [cite: 5]
    FOREIGN KEY (media_id) REFERENCES media_files(id) ON DELETE CASCADE -- 
);


-- (4) boards: 문의 게시판
CREATE TABLE boards (
    id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    title varchar(255) NOT NULL,
    content text NOT NULL,
    readcount INT DEFAULT 0,
    regdate datetime default current_timestamp
);