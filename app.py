from flask import Flask, render_template, request, jsonify, redirect, url_for
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
'''
깃허브 배포 코드
git status
git add .
git commit -m "변경사항 설명"
git push origin main
'''
app = Flask(__name__)

# 로그 레벨 설정 (디버깅용)
logging.basicConfig(level=logging.DEBUG)

DATABASE_URL = "postgresql://postgres.lstjteiebkmacjbekiwl:1318@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"options": "-c client_encoding=utf8"}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_connection():
    return SessionLocal()

@app.route('/')
def index():
    return render_template('index.html')
@app.route('/quiz')
def quiz():
    username = request.args.get('username', '게스트')
    return render_template('quiz.html', username=username)

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    name = data.get('name')

    if not name:
        return jsonify({'success': False, 'message': '이름이 없습니다.'})

    db = get_db_connection()
    try:
        logging.debug(f"회원가입 시도 이름: {name}")
        sql = text("INSERT INTO users (name) VALUES (:name)")
        db.execute(sql, {"name": name})
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"회원가입 실패: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'회원가입 실패: {e}'})
    finally:
        db.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    name = data.get('name')

    if not name:
        return jsonify({'success': False, 'message': '이름을 입력해주세요.'})

    db = get_db_connection()
    try:
        logging.debug(f"로그인 시도 이름: {name}")
        sql = text("SELECT * FROM users WHERE name = :name")
        result = db.execute(sql, {"name": name})
        user = result.fetchone()
        logging.debug(f"조회 결과: {user}")
        if user:
            return jsonify({'success': True, 'redirect': url_for('main', username=name)})
        else:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'})
    except Exception as e:
        logging.error(f"로그인 실패: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'로그인 실패: {e}'})
    finally:
        db.close()

@app.route('/main')
def main():
    username = request.args.get('username', '게스트')
    db = get_db_connection()
    try:
        users_sql = text("SELECT user_id, name, wake_up_time, phone_usage, study_time, score FROM users")
        users_result = db.execute(users_sql)
        users = [dict(row._mapping) for row in users_result.fetchall()]

        for user in users:
            todos_sql = text("SELECT todo_id, task, is_done FROM todos WHERE user_id = :user_id ORDER BY todo_id")
            todos_result = db.execute(todos_sql, {"user_id": user['user_id']})
            todos = [dict(todo._mapping) for todo in todos_result.fetchall()]
            user['todos'] = todos

            if todos:
                done_count = sum(todo['is_done'] for todo in todos)
                user['progress'] = int(done_count / len(todos) * 100)
            else:
                user['progress'] = 0

        ranking_sql = text("SELECT name, COALESCE(score, 0) AS score FROM users ORDER BY score DESC, name ASC")
        ranking_result = db.execute(ranking_sql)
        ranking_list = [dict(row._mapping) for row in ranking_result.fetchall()]

        return render_template('main.html', username=username, user_list=users, ranking_list=ranking_list)
    except Exception as e:
        logging.error(f"main 페이지 로딩 중 오류 발생: {e}", exc_info=True)
        return f"<h2>오류 발생: {e}</h2>"
    finally:
        db.close()

@app.route('/update/<int:user_id>', methods=['POST'])
def update_user(user_id):
    wake_up_time = request.form.get('wake_up_time')
    phone_usage = request.form.get('phone_usage')
    study_time = request.form.get('study_time')

    db = get_db_connection()
    try:
        sql = text("""
            UPDATE users
            SET wake_up_time = :wake_up_time, phone_usage = :phone_usage, study_time = :study_time
            WHERE user_id = :user_id
        """)
        db.execute(sql, {
            "wake_up_time": wake_up_time,
            "phone_usage": phone_usage,
            "study_time": study_time,
            "user_id": user_id
        })
        db.commit()
        return redirect(url_for('main'))
    except Exception as e:
        logging.error(f"업데이트 중 오류 발생: {e}", exc_info=True)
        return f"<h2>업데이트 중 오류 발생: {e}</h2>"
    finally:
        db.close()

def update_progress_and_score(user_id):
    db = get_db_connection()
    try:
        count_sql = text("SELECT COUNT(*) AS total, SUM(is_done::int) AS done FROM todos WHERE user_id = :user_id")
        result = db.execute(count_sql, {"user_id": user_id}).fetchone()
        total = result._mapping['total']
        done = result._mapping['done'] or 0
        progress = int(done / total * 100) if total > 0 else 0

        score_sql = text("SELECT score FROM users WHERE user_id = :user_id")
        current_score = db.execute(score_sql, {"user_id": user_id}).fetchone()._mapping['score'] or 0

        logging.debug(f"[update_progress_and_score] user_id={user_id} total={total} done={done} progress={progress} current_score={current_score}")

        # 진행률 100% 이상일 때마다 1점씩 누적 점수 상승 (무제한)
        if progress >= 100:
            new_score = current_score + 1
            update_sql = text("UPDATE users SET score = :score WHERE user_id = :user_id")
            db.execute(update_sql, {"score": new_score, "user_id": user_id})
            db.commit()
        else:
            # 진행률이 100% 미만이면 점수 유지
            pass
    except Exception as e:
        logging.error(f"점수 업데이트 중 오류: {e}", exc_info=True)
    finally:
        db.close()

@app.route('/add_todo/<int:user_id>', methods=['POST'])
def add_todo(user_id):
    data = request.get_json()
    task = data.get('task')

    if not task or task.strip() == '':
        return jsonify({'success': False, 'message': '할 일을 입력하세요.'})

    db = get_db_connection()
    try:
        sql = text("INSERT INTO todos (user_id, task, is_done) VALUES (:user_id, :task, false)")
        db.execute(sql, {"user_id": user_id, "task": task})
        db.commit()
        update_progress_and_score(user_id)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"할 일 추가 실패: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        db.close()

@app.route('/toggle_todo/<int:todo_id>', methods=['POST'])
def toggle_todo(todo_id):
    db = get_db_connection()
    try:
        select_sql = text("SELECT is_done, user_id FROM todos WHERE todo_id = :todo_id")
        todo = db.execute(select_sql, {"todo_id": todo_id}).fetchone()

        if not todo:
            return jsonify({'success': False, 'message': '할 일을 찾을 수 없습니다.'})

        new_status = not todo._mapping['is_done']

        update_sql = text("UPDATE todos SET is_done = :new_status WHERE todo_id = :todo_id")
        db.execute(update_sql, {"new_status": new_status, "todo_id": todo_id})
        db.commit()

        update_progress_and_score(todo._mapping['user_id'])
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"할 일 상태 토글 실패: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        db.close()

@app.route('/delete_todo/<int:todo_id>', methods=['POST'])
def delete_todo(todo_id):
    db = get_db_connection()
    try:
        select_sql = text("SELECT user_id FROM todos WHERE todo_id = :todo_id")
        todo = db.execute(select_sql, {"todo_id": todo_id}).fetchone()

        if not todo:
            return jsonify({'success': False, 'message': '할 일을 찾을 수 없습니다.'})

        user_id = todo._mapping['user_id']

        delete_sql = text("DELETE FROM todos WHERE todo_id = :todo_id")
        db.execute(delete_sql, {"todo_id": todo_id})
        db.commit()

        update_progress_and_score(user_id)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"할 일 삭제 실패: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        db.close()

@app.route('/delete_all_todos/<int:user_id>', methods=['POST'])
def delete_all_todos(user_id):
    db = get_db_connection()
    try:
        delete_sql = text("DELETE FROM todos WHERE user_id = :user_id")
        db.execute(delete_sql, {"user_id": user_id})
        db.commit()

        update_progress_and_score(user_id)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"전체 할 일 삭제 실패: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        db.close()
@app.route('/update_quiz_score', methods=['POST'])
def update_quiz_score():
    data = request.get_json()
    username = data.get('username')

    if not username:
        return jsonify({'success': False, 'message': '사용자 이름이 없습니다.'})

    db = get_db_connection()
    try:
        # 사용자 정보 조회
        user_sql = text("SELECT user_id, quiz_score, score FROM users WHERE name = :name")
        user = db.execute(user_sql, {"name": username}).fetchone()

        if not user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'})

        quiz_score = (user._mapping['quiz_score'] or 0) + 1
        score = user._mapping['score'] or 0

        if quiz_score >= 30:

            score += 1

        # 업데이트
        update_sql = text("UPDATE users SET quiz_score = :quiz_score, score = :score WHERE user_id = :user_id")
        db.execute(update_sql, {
            "quiz_score": quiz_score,
            "score": score,
            "user_id": user._mapping['user_id']
        })
        db.commit()

        return jsonify({'success': True, 'quiz_score': quiz_score, 'score': score})
    except Exception as e:
        logging.error(f"퀴즈 점수 업데이트 오류: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        db.close()

@app.route('/quiz_ranking')
def quiz_ranking():
    db = get_db_connection()
    try:
        sql = text("SELECT name, quiz_score FROM users ORDER BY quiz_score DESC, name ASC LIMIT 10")
        result = db.execute(sql)
        ranking_list = [dict(row._mapping) for row in result.fetchall()]
        return jsonify({'success': True, 'ranking': ranking_list})
    except Exception as e:
        logging.error(f"랭킹 조회 실패: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        db.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
