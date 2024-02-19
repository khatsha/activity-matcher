from collections import OrderedDict

from flask import Flask, render_template, request, redirect, url_for, session
from wtforms import Form, SelectField, BooleanField, StringField, PasswordField, validators, SelectMultipleField
from flask_login import LoginManager, UserMixin, login_user, current_user, login_required, logout_user
from wtforms.validators import DataRequired
import sqlite3

DEPENDS = 'depends'
SWITCH = "switch"
BOTTOM = "bottom"
TOP = "top"

THE_SWITCH_QUERY_OF_DEATH = """SELECT
tops.partner
FROM
(SELECT partner, activity
FROM activities
WHERE activity='{activity}'
AND name='{name}'
AND role='top') tops
INNER JOIN
(SELECT partner, activity
FROM activities
WHERE activity='{activity2}'
AND name='{name2}'
AND role='bottom') bottoms
ON tops.partner = bottoms.partner
AND tops.activity = bottoms.activity"""

app = Flask(__name__)

app.config.from_object(__name__)
app.config['SECRET_KEY'] = 'EQuahqu9ahhahlei7Xohthaew5osheeC7she'

conn = sqlite3.connect('database.db')
#conn.execute('DROP TABLE activities')
conn.execute('CREATE TABLE IF NOT EXISTS activities (name TEXT, partner TEXT, activity TEXT, role TEXT, UNIQUE(name, partner, activity, role))')
conn.close()

login_manager = LoginManager()
login_manager.init_app(app)

activityTypes = set()
class Activity():
    def __init__(self, name, type):
        self.name = name
        self.hasRole = False
        self.labelToRole = {}
        self.type = type
        activityTypes.add(type)

    def setRoles(self, top, bottom):
        self.hasRole = True
        self.top = top
        self.bottom = bottom
        self.labelToRole[top] = TOP
        self.labelToRole[bottom] = BOTTOM

# load activities
filepath = 'config.txt'
fullActivitiesList = OrderedDict()
with open(filepath) as fp:
    for line in fp:
        tokens = line.split("#")
        if len(tokens) == 2:
            activity = Activity(tokens[1].rstrip(), tokens[0].rstrip())
            fullActivitiesList[activity.name] = activity
        elif len(tokens) == 4:
            activity = Activity(tokens[1].rstrip(), tokens[0].rstrip())
            activity.setRoles(tokens[3].rstrip(), tokens[2].rstrip())
            fullActivitiesList[activity.name] = activity
        else:
            raise ValueError("'" + line + "' should have one type and one activity, or a type, an activity and two roles")

class User(UserMixin):
    def __init__(self, username, password):
        self.id = username
        self.password = password
        self.authenticated = False


    @classmethod
    def get(cls,id):
        # return cls.user_database.get(id)
        if id in fakeUserDb.keys():
            return fakeUserDb[id]
        return None

    def is_active(self):
        """True, as all users are active."""
        return True

    def get_id(self):
        """Return the email address to satisfy Flask-Login's requirements."""
        return self.id

    def is_authenticated(self):
        """Return True if the user is authenticated."""
        return self.authenticated

    def is_anonymous(self):
        """False, as anonymous users aren't supported."""
        return False

fakeUserDb = OrderedDict()
with open("users.txt") as us:
    for line in us:
        tokens = line.split(" ")
        passw = tokens[1].rstrip()
        fakeUserDb[tokens[0]] = User(tokens[0], passw)

partners = []
for partner in fakeUserDb:
    partners.append((partner, partner))

class QuizzConfigForm(Form):
    role = SelectField(u'Role', choices=[(TOP, TOP), (BOTTOM, BOTTOM), (SWITCH, SWITCH), (DEPENDS, DEPENDS)])

@app.route("/quizz", methods=['GET', 'POST'])
def quizz():
    class ReusableForm(Form):
        pass

    if current_user.get_id() is None or current_user.is_authenticated() == False:
        return redirect(url_for('login', next=request.url))

    if request.method == 'POST':
        config = request.form
        config_partners = []
        role = DEPENDS
        types = set()
        for key in config:
            if key == "role":
                role = config[key]
            elif "Type: " in key:
                types.add(key[6:])
            else:
                config_partners.append(key)

        session["config_partners"] = config_partners

        requests = []

        for act in fullActivitiesList.values():
            if act.type in types:
                if not act.hasRole:
                    setNoRoleActivity(act, config_partners, ReusableForm, "")
                    r = "select partner from activities where name = '" + current_user.get_id() +\
                        "' AND activity = '" + act.name + "' AND ( partner = '"
                    orString = "' OR partner = '"
                    r += orString.join(config_partners)
                    r += "')"
                    requests.append((r, act))
                else:
                    if role == DEPENDS:
                        setRoleActivity(act, config_partners, ReusableForm)
                        for p in config_partners:
                            r = "select role from activities where name = '" + current_user.get_id() +\
                               "' AND activity = '" + act.name + "' AND partner = '" + p + "'"
                            requests.append((r, act))
                    else:
                        session["role"] = role
                        if role == SWITCH:
                            r = THE_SWITCH_QUERY_OF_DEATH.format(activity = act.name, name = current_user.get_id(),
                                                                 activity2 = act.name, name2 = current_user.get_id())
                        else:
                            r = "select partner from activities where name = '" + current_user.get_id() +\
                               "' AND activity = '" + act.name + "' AND role = '" + role + "'"
                        requests.append((r, act))

                        roleLabel = getRoleLabel(act, role)
                        roleLabel = " -- " + roleLabel
                        setNoRoleActivity(act, config_partners, ReusableForm, roleLabel)

    form = ReusableForm(request.form)
    set_quizz_defaults(config_partners, form, requests)
    clearUserPastData(config_partners, role)
    return render_template('quizz.html', form=form, user = current_user.get_id())


def set_quizz_defaults(partners, form, requests):
    with sqlite3.connect("database.db") as con:
        for i, field in enumerate(form):
            r = requests[i][0]
            activity = requests[i][1]
            cur = con.cursor()
            cur.execute(r)
            results = cur.fetchall()
            if field.type == "SelectField":
                assert len(results) <= 2, "Only one or two choice should be selected for select fields"
                if len(results) > 0:
                    defaultChoice = ()
                    if len(results) == 2:
                        assert (results[0][0] == TOP and results[1][0] == BOTTOM) \
                               or (results[0][0] == BOTTOM and results[1][0] == TOP), "Only top and bottom can be active " \
                                                                                  "at the same time"
                        defaultChoice = (SWITCH, SWITCH)

                    if len(results) == 1:
                        for choice in field.choices: # Find corresponding choice
                            if choice[0] == getRoleLabel(activity, results[0][0]):
                                defaultChoice = choice
                                break
                    assert defaultChoice != (), "Choice from db doesn't exist in the select field"
                    newChoices = [defaultChoice]
                    for choice in field.choices:
                        if choice != defaultChoice:
                            newChoices.append(choice)
                    field.choices = newChoices
            else:
                defaults = []
                for res in results:
                    defaults.append(res[0])
                field.data = defaults

def getRoleLabel(act, role):
    if role == TOP:
        return act.top
    elif role == BOTTOM:
        return act.bottom
    elif role == SWITCH:
        return SWITCH
    else:
        raise ValueError("Unknown role " + role)

def getRoleFromLabel(act, label):
    if label == SWITCH:
        return SWITCH
    if label not in act.labelToRole:
        raise ValueError("activity " + act.name + " doesnt't have associated role " + label)
    role = act.labelToRole[label]
    return role


def setRoleActivity(act, partners, formClass):
    for p in partners:
        choices = [("0", "No"), (SWITCH, SWITCH)]
        choices.append((act.top, act.top))
        choices.append((act.bottom, act.bottom))
        setattr(formClass, act.name + " # " + p, SelectField(choices=choices))


def setNoRoleActivity(act, partners, formClass, roleText):
    partnerChoice = []
    for p in partners:
        partnerChoice.append((p, p))
    setattr(formClass, act.name + roleText, SelectMultipleField(choices = partnerChoice))


def getMatching(userId):
    matching = OrderedDict()
    try:
        with sqlite3.connect("database.db") as con:
            cur = con.cursor()
            cur.execute("select * from activities where name = '" + userId + "' ORDER BY partner")
            activities = cur.fetchall()
            for activity in activities:
                role = activity[3]
                if role != '0': # user want to do the thing
                    activityPartner = activity[1]
                    activityName = activity[2]
                    cur = con.cursor()
                    cur.execute("select role from activities where name = '" + activityPartner + "' AND activity = '"
                                + activityName + "' AND partner = '" + userId + "'" )
                    partnerRoles = cur.fetchall()
                    if (len(partnerRoles) > 0):
                        for pr in partnerRoles:
                            partner_role = pr[0]

                            if partner_role == "y": #No role
                                matching[activityName + " with " + activityPartner] = "yes"

                            elif partner_role != '0' and  partner_role != role:
                                match = activityName + " with " + activityPartner
                                if match in matching:
                                    # The same activity is already there with a different set of compatible role
                                    # This can have only one explanation: Two Switches!
                                    matching[match] = "any role!"
                                else:
                                    act = fullActivitiesList[activityName]
                                    text = "You said " + getRoleLabel(act, role) + ". They said " \
                                           + getRoleLabel(act, partner_role)
                                    matching[activityName + " with " + activityPartner] = text

    finally:
        return matching


def clearUserPastData(configPartners, role):
    try:
        with sqlite3.connect("database.db") as con:
            if role == DEPENDS or role == SWITCH:
                for p in configPartners:
                    cur = con.cursor()
                    query = "DELETE from activities WHERE name = '" + current_user.get_id() + "' AND partner = '"\
                            + p + "'"
                    cur.execute(query)
                    con.commit()
            else:
                for p in configPartners:
                    cur = con.cursor()
                    query = "DELETE from activities WHERE name = '" + current_user.get_id() + "' AND partner = '"\
                            + p + "' AND role = '" + role + "'"
                    cur.execute(query)
                    con.commit()
    except Exception as err:
        con.rollback()
        raise ValueError('error in db cleaning operation: %s\nError: %s' % (query, str(err)))

    finally:
        con.close()


@app.route('/result',methods = ['POST', 'GET'])
def result():
    if current_user.get_id() is None or current_user.is_authenticated() == False:
        return redirect(url_for('login', next=request.url))

    if request.method == 'POST':
        result = request.form
        try:
            with sqlite3.connect("database.db") as con:
                cur = con.cursor()

                for key in result:
                    values = request.form.getlist(key)
                    for value in values:
                        if value != "0": # We're not recording nos, to save speed and memory
                            partner = value
                            if "#" not in key: # Muli choice with partners. Role has to be inferred
                                if " -- " in key:
                                    act = fullActivitiesList[key.split(" -- ")[0]]
                                else:
                                    act = fullActivitiesList[key]
                                if act.hasRole:  # Role was chosen at config time
                                    role = session["role"]
                                else:  # The activity doesn't have a roles. It has to be yes since we
                                    # filtered out nos earlier
                                    role = "y"
                            else: # multi choice with roles. User chooses role for each activity and partner
                                act = fullActivitiesList[key.split(" # ")[0]]
                                partner = key.split(" # ")[1]
                                role_label = value
                                role = getRoleFromLabel(act, role_label)
                            if role == SWITCH:
                                cur = con.cursor()
                                cur.execute("INSERT OR IGNORE INTO activities (name, partner, activity, role) "
                                            "VALUES(?, ?, ?, ?)",
                                            (current_user.get_id(), partner, act.name, TOP))
                                con.commit()
                                cur = con.cursor()
                                cur.execute("INSERT OR IGNORE INTO activities (name, partner, activity, role) "
                                            "VALUES(?, ?, ?, ?)",
                                            (current_user.get_id(), partner, act.name, BOTTOM))
                                con.commit()
                            else:
                                cur = con.cursor()
                                cur.execute("INSERT OR IGNORE INTO activities (name, partner, activity, role) "
                                            "VALUES(?, ?, ?, ?)",
                                        (current_user.get_id(), partner, act.name, role))
                                con.commit()

        except Exception as err:
            con.rollback()
            raise ValueError("error in db recording operation:" + str(err))

        finally:
            con.close()
    matching = getMatching(current_user.get_id())
    return render_template("result.html", result=matching)

@login_manager.user_loader
def user_loader(user_id):
    return User.get(user_id)


class LoginForm(Form):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        Form.__init__(self, *args, **kwargs)
        self.user = None

    def validate(self):
        if not Form.validate(self):
            return False

        user = User.get(self.username.data)
        if user is None:
            # self.username.errors.append('Unknown username')
            return False
        return True

@app.route('/')
@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm(request.form)
    if form.validate():
        user = User.get(form.username.data)
        if user:
            if user.password == form.password.data:
                user.authenticated = True
                login_user(user, remember=True)
                return redirect(url_for("welcome"))
    return render_template("login.html", form=form)

@app.route("/logout", methods=["GET"])
@login_required
def logout():
    """Logout the current user."""
    user = current_user
    user.authenticated = False
    logout_user()
    return render_template("logout.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User(username, password)
        fakeUserDb[username] = user
        partners.append((username, username))
        return redirect('/login')
    return render_template('signup.html')

@app.route("/welcome")
@login_required
def welcome():
    return render_template("welcome.html", user = current_user.get_id())

@app.route("/quizzConfig")
@login_required
def quizzConfig():
    if current_user.get_id() is None or current_user.is_authenticated() == False:
        return redirect(url_for('login', next=request.url))

    for partner in partners:
        setattr(QuizzConfigForm, partner[0], BooleanField(partner[0]))

    for type in activityTypes:
        setattr(QuizzConfigForm, "Type: " + type, BooleanField("Type: " + type, default=True))
    form = QuizzConfigForm()
    return render_template("quizzConfig.html", user = current_user.get_id(), form = form)

if __name__ =="__main__":
    app.run(host='0.0.0.0',debug=True,port=5000)

