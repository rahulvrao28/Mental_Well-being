from collections import defaultdict

from flask import Flask, render_template, request, flash, redirect, url_for, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import os
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
import math
from mistralai import Mistral
from sqlalchemy import desc
import difflib

app = Flask(__name__)
app.secret_key = 'dev'

# Configuring SQLite database (persistent)
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'Mental_Wellbeing.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------------------------
# Tables Definition
# ---------------------------

class LoginTable(db.Model):
    __tablename__ = 'Login_Table'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(50), nullable=False, unique=True)
    type = db.Column(db.String(50), nullable=False)

class LeaderboardTable(db.Model):
    __tablename__ = 'Leaderboard_Table'
    roll_number = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    club = db.Column(db.String(100), nullable=False)
    streak_days = db.Column(db.Integer, default=0)
    score = db.Column(db.Integer, default=0)
    type = db.Column(db.String(50), nullable=False)

class UserResponseTable(db.Model):
    __tablename__ = 'User_Response_Table'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(20), nullable=False)  # You can also use db.Date
    question_1 = db.Column(db.String(100), nullable=False)
    question_2 = db.Column(db.String(100), nullable=False)
    question_3 = db.Column(db.String(100), nullable=False)

class StreakTable(db.Model):
    __tablename__ = 'Streak_Table'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(50), nullable=False, unique=True)
    last_date = db.Column(db.String(20), nullable=False)  # You can use db.Date
    streak_days = db.Column(db.Integer, default=0)

class ControlTable(db.Model):
    __tablename__ = 'Control_Table'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(20), nullable=False)  # You can also use db.Date


# ---------------------------
# Routes
# ---------------------------

@app.route('/artifact/<filename>')
def artifact_file(filename):
    return send_from_directory('artifact', filename)


@app.route('/user_input/')
def control_user():
    roll_number = request.args.get('roll_number')
    user = LeaderboardTable.query.filter_by(roll_number=roll_number).first()
    source = "../artifact/" + user.club.lower() +"_badge.png"
    return render_template('QControl_Page.html',name=user.name,imageUrl=source)

@app.route('/quiz_page/')
def test_user():
    roll_number = request.args.get('roll_number')
    user = LeaderboardTable.query.filter_by(roll_number=roll_number).first()
    source = "../artifact/" + user.club.lower() + "_badge.png"
    return render_template('Qtest_Page.html', name=user.name, imageUrl=source, roll_number=roll_number)

@app.route('/next_page', methods=['POST'])
def next_page():
    name = request.args.get('name')
    print(name)
    user = LoginTable.query.filter_by(name=name).first()
    roll_number = user.roll_number
    today = datetime.today().date()
    today = today.strftime("%d-%b-%y")

    update_streak(roll_number, today)
    update_control(name, roll_number, today)
    return redirect(url_for('analytical_page', roll_number=roll_number))


def getControlAnalyticsData(roll_number):
    ## Need to be changed
    start_date = '01-JUN-25'
    start_date = datetime.strptime(start_date, '%d-%b-%y').date()
    today = datetime.today().date()
    total_days = today - start_date
    total_days = int(total_days.days)
    user_leaderboard = LeaderboardTable.query.filter_by(roll_number=roll_number).first()
    user_response_days = ControlTable.query.filter_by(roll_number=roll_number).count()
    # return render_template('Leaderboard.html', leaders=leaders)
    user_responses = ControlTable.query.filter_by(roll_number=roll_number).all()
    submitted_dates = []
    for response in user_responses:
        submitted_dates.append(response.date)
    chart_data = generate_weekly_chart_data(start_date, today, submitted_dates)
    streak_days = user_leaderboard.streak_days
    score = user_leaderboard.score
    club = user_leaderboard.club
    badge = club + ' Badge'
    submitted_days = user_response_days
    unsubmitted_days = total_days - submitted_days
    clubLimit = getClubLimit(club)
    progress = round((score * 100) / clubLimit, 0)
    analyticsData = {
        "progress": progress,
        "score": str(score),
        "badgeName": badge,
        "streakDays": streak_days,
        "totalDays": total_days,
        "submittedDays": submitted_days,
        "missedDays": unsubmitted_days,
        "chartData": chart_data
    }
    return analyticsData


@app.route('/analytical_page', methods=['GET','POST'])
def analytical_page():
    roll_number = request.args.get('roll_number')
    if roll_number is None:
        roll_number = request.form.get('roll_number')
    analyticsData = getControlAnalyticsData(roll_number)
    user_leaderboard = LeaderboardTable.query.filter_by(roll_number=roll_number).first()
    club = user_leaderboard.club
    source = "../artifact/" + club.lower() + "_badge.png"
    return render_template('Control_Analytics.html', data=analyticsData, imageUrl=source, roll_number=roll_number)


def update_control(name, roll_number, today):
    new_response = ControlTable(
        name=name,
        roll_number=roll_number,
        date=today
    )
    db.session.add(new_response)
    db.session.commit()

def checkSanity(text, previous):
    matcher0 = difflib.SequenceMatcher(None, text.lower(), previous[0].lower()).ratio() * 100
    matcher1 = difflib.SequenceMatcher(None, text.lower(), previous[1].lower()).ratio() * 100
    if matcher0 > 75 and matcher1 > 75:
        print('similarity error')
        return False
    return True

def checkMeaningful(text,question):
    MISTRAL_API_KEY = 'NG9p92jW3GvBSTCc092FiulLWSH5GhMj'
    model = "mistral-large-latest"

    client = Mistral(api_key=MISTRAL_API_KEY)

    dialogue = f'''
    Answer in Yes/No only for the question

    Is the "{text}" a meaningful answer to the question "{question}"
    '''

    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": dialogue,
                },
            ]
        )
        response = chat_response.choices[0].message.content
    except Exception as e:
        return True

    if 'yes' in response.lower():
        return True
    else:
        print('meaning error')
        return False


def checkValidResponse(answers, previous, question):
    for answer in answers:
        validity = checkSanity(answer, previous) and checkMeaningful(answer, question)
        if not validity:
            return False
    return True


@app.route('/submit_responses', methods=['POST'])
def submit_responses():
    name = request.form.get('name')
    roll_number = request.form.get('roll_number')

    recent_responses = UserResponseTable.query.filter_by(roll_number=roll_number).order_by(desc(UserResponseTable.date)).limit(3).all()

    prevQ1 = []
    prevQ2 = []
    prevQ3 = []

    Question = ["What do you want to do today?", "What are you grateful for today?", "What are your small wins today?"]

    for i in range(1,3):
        prevQ1.append(recent_responses[i].question_1)
        prevQ2.append(recent_responses[i].question_2)
        prevQ3.append(recent_responses[i].question_3)

    goal1 = request.form.get('goals_1')
    goal2 = request.form.get('goals_2')
    goal3 = request.form.get('goals_3')
    goalAnswer = [goal1, goal2, goal3]
    grateful1 = request.form.get('grateful_1')
    grateful2 = request.form.get('grateful_2')
    grateful3 = request.form.get('grateful_3')
    gratefulAnswer = [grateful1, grateful2, grateful3]
    win1 = request.form.get('wins_1')
    win2 = request.form.get('wins_2')
    win3 = request.form.get('wins_3')
    winAnswer = [win1, win2, win3]

    flashFag = False
    flashMessage = "Please Enter Appropriate Response for"

    if not checkValidResponse(goalAnswer, prevQ1, Question[0]):
        flashFag = True
        flashMessage = flashMessage + ' Goals'
    if not checkValidResponse(gratefulAnswer, prevQ2, Question[1]):
        flashFag = True
        flashMessage = flashMessage + ' Grateful'
    if not checkValidResponse(winAnswer, prevQ3, Question[2]):
        flashFag = True
        flashMessage = flashMessage + ' Small Wins'

    if flashFag:
        flash(flashMessage, 'error')
        return redirect(url_for('test_user', roll_number=roll_number))

    q1 = goal1 + ', ' + goal2 + ' and ' +  goal3
    q2 = grateful1 + ', ' +  grateful2 + ' and ' +  grateful3
    q3 = win1 + ', ' +  win2 + ' and ' +  win3

    print(q1,q2,q3)

    today = datetime.today().date()
    today = today.strftime("%d-%b-%y")  # used for display

    # Check if an entry already exists
    existing_entry = UserResponseTable.query.filter_by(roll_number=roll_number, date=today).first()

    if existing_entry:
        # Update the existing record
        existing_entry.name = name
        existing_entry.question_1 = q1
        existing_entry.question_2 = q2
        existing_entry.question_3 = q3
    else:
        # Create new entry
        new_response = UserResponseTable(
            name=name,
            roll_number=roll_number,
            date=today,
            question_1=q1,
            question_2=q2,
            question_3=q3
        )
        db.session.add(new_response)

    db.session.commit()

    update_streak(roll_number,today)
    return redirect(url_for('leaderboard',roll_number=roll_number))

def get_club(score):
    if score < 2000:
        return "Bronze"
    elif score < 5000:
        return "Silver"
    elif score < 15000:
        return "Golden"
    elif score < 35000:
        return "Diamond"
    elif score >= 35000:
        return "Crystal"
    else:
        return "Crystal"

def update_streak(roll_number,date_str):
    try:
        date = datetime.strptime(date_str, '%d-%b-%y').date()
    except ValueError:
        return "Invalid date format. Use dd-MMM-yy", 400

    user_streak = StreakTable.query.filter_by(roll_number=roll_number).first()
    user_leaderboard = LeaderboardTable.query.filter_by(roll_number=roll_number).first()

    if not user_streak or not user_leaderboard:
        return f"No user found with Roll Number: {roll_number}", 404

    last_date = user_streak.last_date
    last_date = datetime.strptime(last_date, '%d-%b-%y').date()

    if last_date and (date - last_date == timedelta(days=1)):
        user_streak.streak_days += 1
    elif date != last_date:
        user_streak.streak_days = 1

    if date != last_date:
        user_leaderboard.score = user_leaderboard.score + user_streak.streak_days * 100

    # if last_date and (date - last_date == timedelta(days=1)):
    #     user_streak.streak_days += 1
    #     user_leaderboard.score = user_leaderboard.score + user_streak.streak_days * 100
    # elif user_streak.streak_days==0:
    #     user_streak.streak_days = 1
    #     user_leaderboard.score = user_leaderboard.score + user_streak.streak_days * 100
    # Update date regardless
    user_streak.last_date = date_str

    # Sync streak + club with leaderboard
    user_leaderboard.streak_days = user_streak.streak_days
    user_leaderboard.club = get_club(user_leaderboard.score)

    db.session.commit()

def getClubLimit(club):
    clubLimit = {'Bronze':2000, 'Silver': 5000, 'Golden': 15000, 'Diamond': 35000}
    return clubLimit[club]


def generate_weekly_chart_data(start_date, end_date, submitted_dates):
    """
    Generate chart data for weekly submission tracking.

    Args:
        start_date (datetime or str): Start date of the period
        end_date (datetime or str): End date of the period
        submitted_dates (list): List of dates when submissions were made

    Returns:
        dict: Chart data in the specified format
    """
    # Convert string dates to datetime objects if needed
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Convert submitted dates to date objects and create a set for fast lookup
    submitted_set = set()
    for date in submitted_dates:
        if isinstance(date, str):
            date = datetime.strptime(date, '%d-%b-%y').date()
        elif isinstance(date, datetime):
            date = date.date()
        submitted_set.add(date)

    # Calculate number of weeks
    total_days = (end_date - start_date).days + 1
    num_weeks = math.ceil(total_days / 7)

    # Initialize data structures
    labels = [f'Week {i + 1}' for i in range(num_weeks)]
    submitted_data = []
    not_submitted_data = []

    # Process each week
    current_date = start_date
    for week in range(num_weeks):
        week_submitted = 0
        week_not_submitted = 0

        # Check each day in the week (or remaining days if last week)
        for day in range(7):
            if current_date > end_date:
                break

            # Check if this date was submitted
            if current_date in submitted_set:
                week_submitted += 1
            else:
                week_not_submitted += 1

            current_date += timedelta(days=1)

        submitted_data.append(week_submitted)
        not_submitted_data.append(week_not_submitted)

    # Return chart data in the requested format
    chart_data = {
        'labels': labels,
        'datasets': [{
            'label': 'Days Submitted',
            'data': submitted_data,
            'backgroundColor': 'rgba(45, 45, 45, 0.8)',
            'borderColor': 'rgba(45, 45, 45, 1)',
            'borderWidth': 2,
            'borderRadius': 5
        }, {
            'label': 'Days Not Submitted',
            'data': not_submitted_data,
            'backgroundColor': 'rgba(160, 160, 160, 0.6)',
            'borderColor': 'rgba(160, 160, 160, 1)',
            'borderWidth': 2,
            'borderRadius': 5
        }]
    }

    return chart_data

def getAnalyticsData(roll_number):
    ## Need to be changed
    start_date = '01-JUN-25'
    start_date = datetime.strptime(start_date, '%d-%b-%y').date()
    today = datetime.today().date()
    total_days = today - start_date
    total_days = int(total_days.days)
    user_leaderboard = LeaderboardTable.query.filter_by(roll_number=roll_number).first()
    user_response_days = UserResponseTable.query.filter_by(roll_number=roll_number).count()
    # return render_template('Leaderboard.html', leaders=leaders)
    user_responses = UserResponseTable.query.filter_by(roll_number=roll_number).all()
    submitted_dates = []
    for response in user_responses:
        submitted_dates.append(response.date)
    chart_data = generate_weekly_chart_data(start_date, today, submitted_dates)
    streak_days = user_leaderboard.streak_days
    score = user_leaderboard.score
    club = user_leaderboard.club
    badge = club + ' Badge'
    submitted_days = user_response_days
    unsubmitted_days = total_days - submitted_days
    clubLimit = getClubLimit(club)
    progress = round((score*100)/clubLimit,0)
    analyticsData = {
        "progress" : progress,
        "score" : str(score),
        "badgeName" : badge,
        "streakDays": streak_days,
        "totalDays": total_days,
        "submittedDays": submitted_days,
        "missedDays": unsubmitted_days,
        "chartData": chart_data
    }
    return analyticsData

@app.route('/leaderboard', methods=['GET','POST'])
def leaderboard():
    roll_number = request.args.get('roll_number')
    if roll_number is None:
        roll_number = request.form.get('roll_number')
    analyticsData = getAnalyticsData(roll_number)
    user_leaderboard = LeaderboardTable.query.filter_by(roll_number=roll_number).first()
    club = user_leaderboard.club
    source = "../artifact/" + club.lower() + "_badge.png"
    return render_template('Analytics_Page.html', data=analyticsData, imageUrl=source, roll_number=roll_number)

@app.route('/download-responses')
def download_responses():
    # Fetch all data from the UserResponseTable
    data = UserResponseTable.query.all()

    # Convert to list of dicts
    data_list = [{
        'Name': row.name,
        'Roll Number': row.roll_number,
        'Date': row.date,
        'Question 1': row.question_1,
        'Question 2': row.question_2,
        'Question 3': row.question_3
    } for row in data]

    # Create a DataFrame
    df = pd.DataFrame(data_list)

    # Write to Excel in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Responses')

    output.seek(0)

    # Send the Excel file as a download
    return send_file(output,
                     download_name='UserResponses.xlsx',
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/download-leaderboard')
def download_leaderboard():
    # Fetch all data from the UserResponseTable
    data = LeaderboardTable.query.all()

    # Convert to list of dicts
    data_list = [{
        'Name': row.name,
        'Roll Number': row.roll_number,
        'Club': row.club,
        'Streak Days': row.streak_days,
        'Type': row.type
    } for row in data]

    # Create a DataFrame
    df = pd.DataFrame(data_list)

    # Write to Excel in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Responses')

    output.seek(0)

    # Send the Excel file as a download
    return send_file(output,
                     download_name='Leaderboard.xlsx',
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/view_response', methods=['POST'])
def view_response():
    roll_number = request.form.get('roll_number')
    data = UserResponseTable.query.filter_by(roll_number=roll_number).all()
    user = LeaderboardTable.query.filter_by(roll_number=roll_number).first()
    club = user.club
    source = "../artifact/" + club.lower() + "_badge.png"
    studentData = {'name': user.name, 'rollNumber': roll_number}
    # Convert to list of dicts
    record = [{
        'date': row.date,
        'question1Response': row.question_1,
        'question2Response': row.question_2,
        'question3Response': row.question_3
    } for row in data]
    studentData['records'] = record
    print(studentData)
    return render_template('Profile_Page.html', data=studentData, imageUrl=source, roll_number=roll_number)


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        roll = request.form.get('roll_number').strip()
        user = LoginTable.query.filter_by(roll_number=roll).first()
        if user:
            if user.type=='Test':
                return redirect(url_for('test_user', roll_number=user.roll_number))
            elif user.type=='Control':
                return redirect(url_for('control_user', roll_number=user.roll_number))
        else:
            flash("Invalid roll number. Please try again.", 'error')

    return render_template('Login_Page.html')

@app.route('/populate_login')
def populate_login():
    # Sample data to insert
    users = [
        LoginTable(name='Rahul V Rao', roll_number='2023PGP270', type='Test'),
        LoginTable(name='Siddhant', roll_number='2020IPM090', type='Control'),
        LoginTable(name='Arnav', roll_number='2020PGP200', type='Test')
    ]

    # Add and commit users
    for user in users:
        existing = LoginTable.query.filter_by(roll_number=user.roll_number).first()
        if not existing:
            db.session.add(user)

    db.session.commit()
    return "Login_Table populated with sample data!"

@app.route('/show_login')
def show_login():
    users = LoginTable.query.all()
    return '<br>'.join([f"{u.id}: {u.name} {u.roll_number} {u.type}" for u in users])

@app.route('/populate_streak')
def populate_streak():
    # Sample data to insert
    users = [
        StreakTable(name='Rahul V Rao', roll_number='2023PGP270', last_date='01-JUN-25', streak_days=0),
        StreakTable(name='Siddhant', roll_number='2020IPM090', last_date='01-JUN-25', streak_days=0),
        StreakTable(name='Arnav', roll_number='2020PGP200', last_date='01-JUN-25', streak_days=9)
    ]

    # Add and commit users
    for user in users:
        existing = StreakTable.query.filter_by(roll_number=user.roll_number).first()
        if not existing:
            db.session.add(user)

    db.session.commit()
    return "Streak_Table populated with sample data!"

@app.route('/populate_leaderboard')
def populate_leaderboard():
    # Sample data to insert
    users = [
        LeaderboardTable(name='Rahul V Rao', roll_number='2023PGP270', club='Bronze', streak_days=0, score=0, type='Test'),
        LeaderboardTable(name='Siddhant', roll_number='2020IPM090', club='Bronze', streak_days=0, score=0, type='Control'),
        LeaderboardTable(name='Arnav', roll_number='2020PGP200', club='Bronze', streak_days=9, score=0, type='Test')
    ]

    # Add and commit users
    for user in users:
        existing = LeaderboardTable.query.filter_by(roll_number=user.roll_number).first()
        if not existing:
            db.session.add(user)

    db.session.commit()
    return "LeaderboardTable populated with sample data!"

@app.route('/show_leaderboard')
def show_leaderboard():
    users = LeaderboardTable.query.all()
    return '<br>'.join([f"{u.name} {u.roll_number} {u.club} {u.streak_days} {u.type}" for u in users])


@app.route('/show_streak')
def show_streak():
    users = StreakTable.query.all()
    return '<br>'.join([f"{u.id}: {u.name} {u.roll_number} {u.last_date} {u.streak_days}" for u in users])


@app.route('/show_responses')
def show_responses():
    users = UserResponseTable.query.all()
    return '<br>'.join([f"{u.id}: {u.name} {u.roll_number} {u.date} {u.question_1} {u.question_2} {u.question_3}" for u in users])

# main driver function
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()

