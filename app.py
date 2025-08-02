from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
import bleach
import hashlib
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
import secrets
from dotenv import load_dotenv

load_dotenv()


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)




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



# TODO: Create a User table for all your registered users.
class User(UserMixin, db.Model):
    __tablename__ = "user_table"

    id: Mapped[int] = mapped_column(primary_key=True)
    username : Mapped[str]
    email : Mapped[str]
    password : Mapped[str]

    posts : Mapped[List["BlogPost"]] = relationship(back_populates="author")
    comments : Mapped[List["Comment"]] = relationship(back_populates="author")


# CONFIGURE TABLES
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

# TODO: create a comment table
class Comment(db.Model):
    __tablename__ = "comments"
    post_id :Mapped[int] = mapped_column(ForeignKey("blog_posts.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("user_table.id"))
    parent_post: Mapped["BlogPost"] = relationship(back_populates="comments")
    author : Mapped["User"] = relationship(back_populates="comments")
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)




with app.app_context():
    db.create_all()

# create an admin only decorator
def admin_only(function):
    @wraps(function)
    def wrapper(**kwargs):
        if current_user.id == 1:
            return function()
        else:
            abort(403)
    return wrapper

# Create a user_loader callback
@login_manager.user_loader
def load_user(user_id):
    return db.session.scalar(db.select(User).where(User.id == user_id) )

# TODO: Use Werkzeug to hash the user's password when creating a new user.
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


# TODO: Retrieve a user from the database based on their email. 
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


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()

    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
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


# TODO: Use a decorator so only an admin user can create a new post
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
# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
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


# TODO: Use a decorator so only an admin user can delete a post
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


@app.route("/contact")
def contact():
    return render_template("contact.html")

if __name__ == "__main__":
    app.run(debug=False, port=5001)

