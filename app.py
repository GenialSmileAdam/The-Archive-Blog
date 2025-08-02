from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request, jsonify
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
import bleach
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, exists, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from typing import List
# Import your forms from the forms.py
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
import os
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from email.message import EmailMessage
import smtplib


load_dotenv()




app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)
# CSFR protection
csrf = CSRFProtect(app)



# TODO: Configure Flask-Login
login_manager  = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URI",'sqlite:///posts.db')
db = SQLAlchemy(model_class=Base)
db.init_app(app)

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

# Input sanitization
def strip_invalid_html(content):
    allowed_tags = ['a', 'abbr', 'acronym', 'address', 'b', 'br', 'div', 'dl', 'dt',
                    'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img',
                    'li', 'ol', 'p', 'pre', 'q', 's', 'small', 'strike',
                    'span', 'sub', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th',
                    'thead', 'tr', 'tt', 'u', 'ul']

    allowed_attrs = {
        'a': ['href', 'target', 'title'],
        'img': ['src', 'alt', 'width', 'height'],
    }

    cleaned = bleach.clean(content,
                           tags=allowed_tags,
                           attributes=allowed_attrs,
                           strip=True)

    return cleaned

# Email functionality
TO_EMAIL = os.getenv('TO_EMAIL')
MY_EMAIL = os.getenv('MY_EMAIL')
MY_PASSWORD = os.getenv('MY_PASSWORD')

def send_email(body):


    message = EmailMessage()
    message.set_payload(body, 'utf-8')
    message.add_header('Subject', 'A Letter from the Archive')
    message.add_header('To', TO_EMAIL)

    with smtplib.SMTP('smtp.gmail.com', port=587) as connection:
        connection.starttls()
        connection.login(user=MY_EMAIL, password=MY_PASSWORD)
        connection.send_message(msg=message, )

# User table
class User(UserMixin, db.Model):
    __tablename__ = "user_table"

    id: Mapped[int] = mapped_column(primary_key=True)
    username : Mapped[str]
    email : Mapped[str]
    password : Mapped[str]

    posts : Mapped[List["BlogPost"]] = relationship(back_populates="author")
    comments : Mapped[List["Comment"]] = relationship(back_populates="author")

    def to_dict(self):
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}

# Blog post table
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    author_id: Mapped[int] = mapped_column(ForeignKey("user_table.id"))

    author : Mapped["User"] = relationship(back_populates="posts")
    comments: Mapped[List["Comment"]] = relationship(back_populates="parent_post")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)


    def to_dict(self):
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


#  comment table
class Comment(db.Model):
    __tablename__ = "comments"
    post_id :Mapped[int] = mapped_column(ForeignKey("blog_posts.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("user_table.id"))
    parent_post: Mapped["BlogPost"] = relationship(back_populates="comments")
    author : Mapped["User"] = relationship(back_populates="comments")
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)



#
# with app.app_context():
#     db.create_all()


# an admin only decorator
def admin_only(function):
    @wraps(function)
    def wrapper(**kwargs):
        if current_user.id == 1:
            return function()
        else:
            abort(403)
    return wrapper

#  user_loader callback
@login_manager.user_loader
def load_user(user_id):
    return db.session.scalar(db.select(User).where(User.id == user_id) )



@app.route('/register', methods= ["POST", "GET"])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        username = form.username.data
        email= form.email.data
        password= generate_password_hash(form.password.data, method="pbkdf2:sha256", salt_length=8)

        user_exists = db.session.query(exists().where((User.email == email))).scalar()

        if not user_exists:
            new_user = User(email = email,#type:ignore
                            password=password,#type:ignore
                            username= username) #type:ignore
            db.session.add(new_user)
            db.session.commit()

            # login and redirect user to the homepage
            login_user(new_user)
            flash("Registration Successful")
            return redirect(url_for("get_all_posts"))
        else:
            flash("User already exists under that email! log in instead")
            return redirect(url_for("login"))

    return render_template("register.html", form = form)


@app.route('/login', methods= ["POST","GET"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        user_exists = db.session.query(exists().where((User.email == email))).scalar()

        if user_exists:
            user = db.session.scalar(db.select(User).where(User.email == email))
            if check_password_hash(pwhash=user.password,
                                password=password):
                login_user(user)
                flash("Login Successful")
                return redirect(url_for("get_all_posts"))
            else:
                flash("Password is Incorrect, Try again.")
        else:
            flash("User does not exist, Register.")
    return render_template("login.html", form= form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for('get_all_posts'))

#   API functionality

@app.route("/get-all-posts", methods= ["GET"])
def retrieve_all_posts():
    posts = db.session.scalars(db.select(BlogPost))
    list_of_posts = [post.to_dict() for post in posts]

    if request.args.get("password") == os.environ.get("ADMIN_PASSWORD"):
        return jsonify(num_of_posts = len(list_of_posts), posts=list_of_posts), 200
    else:
        abort(401)

@app.route("/get-all-users", methods= ["GET"])
def retrieve_all_users():
    users = db.session.scalars(db.select(User))
    list_of_users = [post.to_dict() for post in users]

    if request.args.get("password") == os.environ.get("ADMIN_PASSWORD"):
        return jsonify(num_of_users = len(list_of_users), posts=list_of_users), 200
    else:
        abort(401)


# regular routes
@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()

    return render_template("index.html", all_posts=posts)


@app.route("/post/<int:post_id>", methods=["POST","GET"])
def show_post(post_id):
    form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    if form.validate_on_submit():
        if current_user.is_active:

            comment = strip_invalid_html(form.comment.data)
            print(comment)
            new_comment = Comment(text = comment,
                                  parent_post = requested_post,
                                  author= current_user)
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for("show_post", post_id= post_id))
        else:
            flash("You have to be logged in to comment on that post.")
            return redirect(url_for("login"))
    return render_template("post.html", post=requested_post, form= form)


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


@app.route("/edit-post", methods=["GET", "POST"])
@admin_only
def edit_post():
    post_id = request.args.get("post_id")
    post  = db.session.scalar(db.select(BlogPost).where(BlogPost.id == post_id))


    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=['POST','GET'])
def contact():
    if request.method == 'POST':
        data = request.form
        name = data['name']
        email = data['email']
        phone= data['phone']
        message = data['message']
        send_email(f"Name: {name}\n"
                   f"Email: {email}\n"
                   f"Phone No : {phone}\n"
                   f"Message: {message}")

        flash('Successfully sent your message')

    return render_template("contact.html")

if __name__ == "__main__":
    app.run(debug=False, port=5001)

