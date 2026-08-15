from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from models import db
from models.user import User
from models.course import Course, CourseRegistration
from models.qr_session import QRSession
from models.attendance import Attendance
from utils.decorators import lecturer_required
from utils.qr_generator import generate_qr_code, generate_attendance_url
from datetime import datetime
import pandas as pd
from io import BytesIO
from flask import send_file


lecturer = Blueprint('lecturer', __name__, url_prefix='/lecturer')


@lecturer.route('/dashboard')
@login_required
@lecturer_required
def dashboard():
    """Lecturer dashboard"""
    courses = Course.query.filter_by(lecturer_id=current_user.id).all()

    # Get statistics
    total_courses = len(courses)
    total_students = sum(
        [course.get_registered_students_count() for course in courses]
    )

    # Get recent attendance sessions
    recent_sessions = QRSession.query.join(Course).filter(
        Course.lecturer_id == current_user.id
    ).order_by(QRSession.generated_at.desc()).limit(5).all()

    return render_template(
        'lecturer/dashboard.html',
        courses=courses,
        total_courses=total_courses,
        total_students=total_students,
        recent_sessions=recent_sessions
    )


@lecturer.route('/courses')
@login_required
@lecturer_required
def courses():
    """View lecturer's courses"""
    lecturer_courses = Course.query.filter_by(
        lecturer_id=current_user.id
    ).all()

    return render_template(
        'lecturer/courses.html',
        courses=lecturer_courses
    )


@lecturer.route('/course/<int:course_id>')
@login_required
@lecturer_required
def course_detail(course_id):
    """View course details"""
    course = Course.query.get_or_404(course_id)

    # Verify lecturer owns this course
    if course.lecturer_id != current_user.id:
        flash(
            'You do not have permission to view this course.',
            'danger'
        )
        return redirect(url_for('lecturer.dashboard'))

    # Get registered students
    registrations = CourseRegistration.query.filter_by(
        course_id=course_id
    ).all()

    students = [
        User.query.get(reg.student_id)
        for reg in registrations
    ]

    # Get attendance sessions
    sessions = QRSession.query.filter_by(
        course_id=course_id
    ).order_by(
        QRSession.generated_at.desc()
    ).all()

    return render_template(
        'lecturer/course_detail.html',
        course=course,
        students=students,
        sessions=sessions
    )


@lecturer.route(
    '/register-students/<int:course_id>',
    methods=['GET', 'POST']
)
@login_required
@lecturer_required
def register_students(course_id):
    """Register students for a course"""
    course = Course.query.get_or_404(course_id)

    # Verify lecturer owns this course
    if course.lecturer_id != current_user.id:
        flash(
            'You do not have permission to modify this course.',
            'danger'
        )
        return redirect(url_for('lecturer.dashboard'))

    if request.method == 'POST':
        student_ids = request.form.getlist('student_ids')

        registered_count = 0

        for student_id in student_ids:
            # Check if already registered
            existing = CourseRegistration.query.filter_by(
                student_id=student_id,
                course_id=course_id
            ).first()

            if not existing:
                registration = CourseRegistration(
                    student_id=student_id,
                    course_id=course_id
                )

                db.session.add(registration)
                registered_count += 1

        db.session.commit()

        flash(
            f'{registered_count} student(s) registered successfully!',
            'success'
        )

        return redirect(
            url_for(
                'lecturer.course_detail',
                course_id=course_id
            )
        )

    # Get all students
    all_students = User.query.filter_by(
        role='student'
    ).order_by(
        User.full_name
    ).all()

    # Get already registered students
    registered = CourseRegistration.query.filter_by(
        course_id=course_id
    ).all()

    registered_ids = [
        reg.student_id
        for reg in registered
    ]

    return render_template(
        'lecturer/register_students.html',
        course=course,
        students=all_students,
        registered_ids=registered_ids
    )


@lecturer.route(
    '/unregister-student/<int:course_id>/<int:student_id>',
    methods=['POST']
)
@login_required
@lecturer_required
def unregister_student(course_id, student_id):
    """Unregister a student from a course"""
    course = Course.query.get_or_404(course_id)

    # Verify lecturer owns this course
    if course.lecturer_id != current_user.id:
        flash(
            'You do not have permission to modify this course.',
            'danger'
        )
        return redirect(url_for('lecturer.dashboard'))

    registration = CourseRegistration.query.filter_by(
        student_id=student_id,
        course_id=course_id
    ).first()

    if registration:
        db.session.delete(registration)
        db.session.commit()

        flash(
            'Student unregistered successfully.',
            'success'
        )
    else:
        flash(
            'Student not found in this course.',
            'warning'
        )

    return redirect(
        url_for(
            'lecturer.course_detail',
            course_id=course_id
        )
    )


@lecturer.route(
    '/generate-qr/<int:course_id>',
    methods=['GET', 'POST']
)
@login_required
@lecturer_required
def generate_qr(course_id):
    """Generate QR code for attendance"""
    course = Course.query.get_or_404(course_id)

    # Verify lecturer owns this course
    if course.lecturer_id != current_user.id:
        flash(
            'You do not have permission to generate QR for this course.',
            'danger'
        )
        return redirect(url_for('lecturer.dashboard'))

    if request.method == 'POST':
        # Deactivate any previous active sessions for this course
        old_sessions = QRSession.query.filter_by(
            course_id=course_id,
            is_active=True
        ).all()

        for session in old_sessions:
            session.deactivate()

        # Create new QR session
        qr_session = QRSession.create_session(
            course_id,
            expiration_minutes=15
        )

        # Generate QR code URL using the configured application base URL.
        #
        # Local development:
        # http://192.168.1.34:5000
        #
        # Render:
        # https://your-attendance-system.onrender.com
        attendance_url = generate_attendance_url(
            current_app.config["APP_BASE_URL"],
            qr_session.qr_code_data
        )

        # Generate QR code image
        qr_image = generate_qr_code(attendance_url)

        return render_template(
            'lecturer/display_qr.html',
            course=course,
            qr_session=qr_session,
            qr_image=qr_image,
            attendance_url=attendance_url
        )

    return render_template(
        'lecturer/generate_qr.html',
        course=course
    )


@lecturer.route('/attendance-session/<int:session_id>')
@login_required
@lecturer_required
def attendance_session(session_id):
    """View attendance for a QR session"""
    qr_session = QRSession.query.get_or_404(session_id)
    course = qr_session.course

    # Verify lecturer owns this course
    if course.lecturer_id != current_user.id:
        flash(
            'You do not have permission to view this session.',
            'danger'
        )
        return redirect(url_for('lecturer.dashboard'))

    # Get attendance records
    attendance_records = Attendance.query.filter_by(
        qr_session_id=session_id
    ).all()

    # Get student details
    students_present = []

    for record in attendance_records:
        student = User.query.get(record.student_id)

        students_present.append({
            'student': student,
            'marked_at': record.marked_at
        })

    # Get all registered students for this course
    all_registrations = CourseRegistration.query.filter_by(
        course_id=course.id
    ).all()

    total_registered = len(all_registrations)

    return render_template(
        'lecturer/attendance_session.html',
        qr_session=qr_session,
        course=course,
        students_present=students_present,
        total_present=len(students_present),
        total_registered=total_registered
    )


@lecturer.route('/attendance-live/<int:session_id>')
@login_required
@lecturer_required
def attendance_live(session_id):
    """Get live attendance data (AJAX endpoint)"""
    qr_session = QRSession.query.get_or_404(session_id)
    course = qr_session.course

    # Verify lecturer owns this course
    if course.lecturer_id != current_user.id:
        return jsonify({
            'error': 'Unauthorized'
        }), 403

    # Get attendance records
    attendance_records = Attendance.query.filter_by(
        qr_session_id=session_id
    ).order_by(
        Attendance.marked_at.desc()
    ).all()

    students_data = []

    for record in attendance_records:
        student = User.query.get(record.student_id)

        students_data.append({
            'name': student.full_name,
            'matric': student.matric_number,
            'time': record.marked_at.strftime('%I:%M:%S %p')
        })

    # Get total registered
    total_registered = CourseRegistration.query.filter_by(
        course_id=course.id
    ).count()

    return jsonify({
        'students': students_data,
        'total_present': len(students_data),
        'total_registered': total_registered,
        'is_expired': qr_session.is_expired()
    })


@lecturer.route('/export-attendance/<int:session_id>')
@login_required
@lecturer_required
def export_attendance(session_id):
    """Export attendance to Excel"""
    qr_session = QRSession.query.get_or_404(session_id)
    course = qr_session.course

    # Verify lecturer owns this course
    if course.lecturer_id != current_user.id:
        flash(
            'You do not have permission to export this data.',
            'danger'
        )
        return redirect(url_for('lecturer.dashboard'))

    # Get attendance records
    attendance_records = Attendance.query.filter_by(
        qr_session_id=session_id
    ).all()

    # Prepare data
    data = []

    for record in attendance_records:
        student = User.query.get(record.student_id)

        data.append({
            'Matric Number': student.matric_number,
            'Full Name': student.full_name,
            'Email': student.email,
            'Time Marked': record.marked_at.strftime(
                '%Y-%m-%d %I:%M:%S %p'
            )
        })

    # Create DataFrame
    df = pd.DataFrame(data)

    # Create Excel file in memory
    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine='openpyxl'
    ) as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name='Attendance'
        )

    output.seek(0)

    filename = (
        f"attendance_{course.course_code}_"
        f"{qr_session.generated_at.strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

    return send_file(
        output,
        mimetype=(
            'application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.sheet'
        ),
        as_attachment=True,
        download_name=filename
    )


@lecturer.route('/attendance-history/<int:course_id>')
@login_required
@lecturer_required
def attendance_history(course_id):
    """View attendance history for a course"""
    course = Course.query.get_or_404(course_id)

    # Verify lecturer owns this course
    if course.lecturer_id != current_user.id:
        flash(
            'You do not have permission to view this course.',
            'danger'
        )
        return redirect(url_for('lecturer.dashboard'))

    # Get all sessions for this course
    sessions = QRSession.query.filter_by(
        course_id=course_id
    ).order_by(
        QRSession.generated_at.desc()
    ).all()

    session_data = []

    for session in sessions:
        attendance_count = Attendance.query.filter_by(
            qr_session_id=session.id
        ).count()

        session_data.append({
            'session': session,
            'attendance_count': attendance_count
        })

    return render_template(
        'lecturer/attendance_history.html',
        course=course,
        session_data=session_data
    )