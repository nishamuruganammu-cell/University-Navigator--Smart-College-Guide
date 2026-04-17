from flask import Flask, render_template, request, redirect, session
import pandas as pd
from sklearn.neighbors import NearestNeighbors
import re
import requests
app = Flask(__name__)
app.secret_key = "secret"

# ================= LOAD DATA =================
FIELD_KEYWORDS = {
    "engineering": ["technology", "engineering", "science"],
    "medical": ["medical", "health"],
    "business": ["business", "economics", "management"],
    "arts": ["arts", "design"],
    "law": ["law"]
}

df = pd.read_csv("dataset/processed.csv", encoding="latin1")
df.columns = df.columns.str.strip()

# 🔥 Convert to numeric (fix hidden errors)
df["greV"] = pd.to_numeric(df["greV"], errors="coerce")
df["greQ"] = pd.to_numeric(df["greQ"], errors="coerce")
df["greA"] = pd.to_numeric(df["greA"], errors="coerce")
df["cgpa"] = pd.to_numeric(df["cgpa"], errors="coerce")

# 🔥 REMOVE NULL VALUES (MOST IMPORTANT FIX)
df = df.dropna(subset=["greV", "greQ", "greA", "cgpa"])

# Features
df["GRE"] = df["greV"] + df["greQ"] + df["greA"]
df["GPA"] = df["cgpa"]

X = df[["GRE", "GPA"]]
model = NearestNeighbors(n_neighbors=5)
model.fit(X)

details_df = pd.read_csv("dataset/university_details.csv", encoding="latin1")
details_df.columns = details_df.columns.str.strip()

# Clean names
details_df["University Name"] = details_df["University Name"].astype(str).str.strip()

# ❌ Remove rows with no real name
details_df = details_df[
    details_df["University Name"].notna()
]

# ❌ Remove numeric / garbage values like 601, 801
details_df = details_df[
    details_df["University Name"].str.contains("[A-Za-z]", na=False)
]

# ❌ Remove only-number names
details_df = details_df[
    ~details_df["University Name"].str.match(r'^\d+$')
]

# ❌ Remove duplicates
details_df = details_df.drop_duplicates(subset=["University Name"])

# ✅ Reset index (IMPORTANT)
details_df = details_df.reset_index(drop=True)

# ✅ Fill missing values
details_df = details_df.fillna("N/A")


sch_df = pd.read_csv(
    "dataset/scholarships.csv",
    encoding="latin1",
    on_bad_lines="skip"   # 🔥 THIS FIXES BROKEN ROWS
)
# Clean column names
sch_df.columns = sch_df.columns.str.strip()

# clean location column
sch_df["location"] = sch_df["location"].astype(str).str.strip().str.lower()

# remove empty / garbage
sch_df = sch_df[sch_df["location"] != ""]
sch_df = sch_df[sch_df["location"] != "nan"]

# get all unique countries
countries = sorted(sch_df["location"].unique().tolist())



# ================= FUNCTIONS =================

def recommend_universities(greV, greQ, greA, cgpa):

    try:
        gre = float(greV) + float(greQ) + float(greA)
        cgpa = float(cgpa)
    except:
        return []

    user = [[gre, cgpa]]

    # 🔥 get nearest universities
    distances, indices = model.kneighbors(user, n_neighbors=20)

    temp_df = df.iloc[indices[0]].copy()

    # 🔥 sort by best match (closest distance)
    temp_df["distance"] = distances[0]

    result = (
        temp_df
        .sort_values(by="distance")   # closest first
        [["univName"]]
        .drop_duplicates()
        .head(5)
    )

    print("RESULT:", result)

    return result.to_dict(orient="records")

def get_scholarships(degree, location):
    df = sch_df.copy()

    df["location"] = df["location"].str.lower().str.strip()
    df["degrees"] = df["degrees"].str.lower()

    degree = degree.lower().strip()
    location = location.lower().strip()

    result = df[
        df["degrees"].str.contains(degree, na=False) &
        df["location"].str.contains(location, na=False)
    ]

    return result.to_dict(orient="records") 



def get_intent(text):
    text = text.lower()

    intent = {
        "type": "general",
        "country": None,
        "metric": None,
        "cgpa": None,
        "compare": False
    }

    # -----------------------
    # 🎯 TYPE DETECTION
    # -----------------------
    if any(word in text for word in ["scholarship", "fund", "money", "aid"]):
        intent["type"] = "scholarship"

    elif any(word in text for word in ["compare", "vs"]):
        intent["type"] = "compare"
        intent["compare"] = True

    elif any(word in text for word in ["university", "college", "top", "best", "rank"]):
        intent["type"] = "university"

    # -----------------------
    # 🌍 COUNTRY DETECTION
    # -----------------------
    countries = ["canada", "usa", "united states", "uk", "india", "australia", "germany", "japan"]

    for c in countries:
        if c in text:
            intent["country"] = c
            break

    # -----------------------
    # 📊 METRIC DETECTION
    # -----------------------
    if "research" in text:
        intent["metric"] = "research_score"
    elif "teaching" in text:
        intent["metric"] = "teaching_score"
    elif "citations" in text:
        intent["metric"] = "citations_score"
    elif "industry" in text:
        intent["metric"] = "industry_income_score"
    elif "international" in text:
        intent["metric"] = "international_outlook_score"
    else:
        intent["metric"] = "overall_score"

    # -----------------------
    # 🎓 CGPA DETECTION
    # -----------------------
    import re
    numbers = re.findall(r"\d+\.?\d*", text)
    if numbers:
        intent["cgpa"] = float(numbers[0])

    return intent


# ================= ROUTES =================

@app.route("/")
def home():
    return render_template("home.html", logged_in=session.get("logged_in"))


# 🔐 LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "1234":
            session["logged_in"] = True
            return redirect("/")
        else:
            error = "Invalid login"

    return render_template("login.html", error=error)


# 🎓 GRADUATE (PROTECTED)
@app.route("/graduate", methods=["GET", "POST"])
def graduate():
    if not session.get("logged_in"):
        return redirect("/login")

    universities = None

    if request.method == "POST":

        print("FORM DATA:", request.form)

        try:
            greV = request.form["greV"]
            greQ = request.form["greQ"]
            greA = request.form["greA"]
            cgpa = request.form["cgpa"]

            # ❌ REMOVE FIELD
            universities = recommend_universities(
                greV, greQ, greA, cgpa
            )

            print("Universities:", universities)

        except Exception as e:
            print("ERROR:", e)
            universities = []

    return render_template("graduate.html", universities=universities)

# 🎓 UNDERGRADUATE (PROTECTED)
@app.route("/undergraduate", methods=["GET", "POST"])
def undergraduate():

    if not session.get("logged_in"):
        return redirect("/login")

    universities = []

    if request.method == "POST":
        try:
            marks = float(request.form["marks"])
            cgpa = float(request.form["cgpa"])

            temp_df = df.copy()

            # 🔥 NORMALIZE VALUES (important)
            marks_norm = marks / 100        # assuming marks out of 100
            cgpa_norm = cgpa / 10           # assuming cgpa out of 10

            # 🔥 BALANCED SCORE
            temp_df["score"] = (cgpa_norm * 0.6) + (marks_norm * 0.4)

            universities = (
                temp_df
                .sort_values("score", ascending=False)
                .drop_duplicates(subset=["univName"])
                .head(5)[["univName"]]
                .to_dict(orient="records")
            )

            print("UG RESULT:", universities)

        except Exception as e:
            print("ERROR:", e)
            universities = []

    return render_template("undergraduate.html", universities=universities)

# ⚖️ COMPARE (PROTECTED)
@app.route("/compare", methods=["GET", "POST"])
def compare():
    if not session.get("logged_in"):
        return redirect("/login")

    result = []
    error = ""

    # ✅ unique countries
    countries = sorted(details_df["Country"].dropna().unique().tolist())

    # default names
    filtered_df = details_df.copy()

    if request.method == "POST":
        u1 = request.form.get("uni1")
        u2 = request.form.get("uni2")
        country = request.form.get("country")

        # ✅ apply country filter
        if country:
            filtered_df = filtered_df[filtered_df["Country"] == country]

        # ✅ get results ONLY for selected universities
        result = filtered_df[
            filtered_df["University Name"].isin([u1, u2])
        ].drop_duplicates(subset=["University Name"]).to_dict(orient="records")

        # ❌ if not exactly 2 universities
        if len(result) != 2:
            error = "⚠️ Please select valid universities (after filtering)"

    names = sorted(filtered_df["University Name"].unique().tolist())

    return render_template(
        "compare.html",
        result=result,
        names=names,
        countries=countries,
        error=error
    )

# 💰 SCHOLARSHIP (PROTECTED)
@app.route("/scholarship", methods=["GET", "POST"])
def scholarship():
    if not session.get("logged_in"):
        return redirect("/login")

    scholarships = []

    # ✅ get unique countries dynamically
    countries = sorted(sch_df["location"].dropna().unique())

    if request.method == "POST":
        degree = request.form.get("degree", "").strip()
        location = request.form.get("location", "").strip()

        scholarships = get_scholarships(degree, location)

    return render_template(
        "scholarship.html",
        scholarships=scholarships,
        countries=countries
    )


# 🤖 CHAT (PROTECTED)


@app.route("/chat", methods=["GET", "POST"])
def chat():

    if not session.get("logged_in"):
        return redirect("/login")

    if "chat_history" not in session:
        session["chat_history"] = []

    if request.method == "POST":
        user_input = request.form.get("message", "").lower().strip()

        # COPY DATA
        df_uni = details_df.copy()
        df_sch = sch_df.copy()
        df_proc = df.copy()

        response = []

        # -------------------------------
        # 🧹 CLEAN DATA
        # -------------------------------
        df_uni.columns = df_uni.columns.str.strip()
        df_uni["Country"] = df_uni["Country"].astype(str).str.lower()

        df_sch.columns = df_sch.columns.str.strip().str.lower()
        df_sch["location"] = df_sch["location"].astype(str).str.lower()

        df_proc.columns = df_proc.columns.str.strip()

        # -------------------------------
        # 🔍 EXTRACT CGPA
        # -------------------------------
        numbers = re.findall(r"\d+\.?\d*", user_input)
        cgpa = float(numbers[0]) if numbers else None

        # -------------------------------
        # 🌍 COUNTRY DETECTION
        # -------------------------------
        selected_country = None
        for c in df_uni["Country"].unique():
            if c in user_input:
                selected_country = c
                break

        # -------------------------------
        # 📊 METRIC DETECTION
        # -------------------------------
        metric_map = {
            "research": "research_score",
            "teaching": "teaching_score",
            "citations": "citations_score",
            "industry": "industry_income_score",
            "international": "international_outlook_score",
            "overall": "overall_score"
        }

        selected_metric = "overall_score"
        for key in metric_map:
            if key in user_input:
                selected_metric = metric_map[key]

        # =====================================================
        # ⚖️ COMPARE UNIVERSITIES
        # =====================================================
        if "compare" in user_input or "vs" in user_input:

            names = df_uni["University Name"].astype(str).tolist()
            found = []

            for name in names:
                if name.lower() in user_input:
                    found.append(name)

            if len(found) >= 2:
                u1 = df_uni[df_uni["University Name"] == found[0]].iloc[0]
                u2 = df_uni[df_uni["University Name"] == found[1]].iloc[0]

                better = found[0] if float(u1["overall_score"]) > float(u2["overall_score"]) else found[1]

                response = [{
                    "Type": "Comparison",
                    "Universities": f"{found[0]} vs {found[1]}",
                    "Overall Score": f"{u1['overall_score']} vs {u2['overall_score']}",
                    "Research": f"{u1['research_score']} vs {u2['research_score']}",
                    "Teaching": f"{u1['teaching_score']} vs {u2['teaching_score']}",
                    "Better University": better
                }]
            else:
                response = [{"Message": "Type full names like: compare Oxford and Cambridge"}]

        else:
            # =====================================================
            # 🎓 UNIVERSITY RESULTS
            # =====================================================
            uni_results = df_uni.copy()

            if selected_country:
                uni_results = uni_results[
                    uni_results["Country"].str.contains(selected_country, na=False)
                ]

            if cgpa:
                if cgpa >= 9:
                    uni_results = uni_results[uni_results["overall_score"].astype(float) > 70]
                elif cgpa >= 8:
                    uni_results = uni_results[uni_results["overall_score"].astype(float) > 50]

            uni_results = uni_results.sort_values(selected_metric, ascending=False).head(5)

            # =====================================================
            # 🎯 KNN RECOMMENDATION
            # =====================================================
            if cgpa:
                temp = df_proc.copy()
                temp["diff"] = abs(temp["cgpa"] - cgpa)
                knn_results = temp.sort_values("diff").head(5)
            else:
                knn_results = pd.DataFrame()

            # =====================================================
            # 💰 SCHOLARSHIPS
            # =====================================================
            sch_results = df_sch.copy()

            if selected_country:
                sch_results = sch_results[
                    sch_results["location"].str.contains(selected_country, na=False)
                ]

            sch_results = sch_results.head(5)

            # -------------------------------
            # BUILD RESPONSE
            # -------------------------------
            # UNIVERSITIES
            if not uni_results.empty:
                for _, row in uni_results.iterrows():
                    response.append({
                        "Type": "University",
                        "Name": row.get("University Name", "N/A"),
                        "Country": row.get("Country", "N/A"),
                        "Score": row.get(selected_metric, "N/A"),
                        "Website": row.get("Link", "N/A"),
                        "Description": str(row.get("description", ""))[:120] + "..."
                    })

            # KNN MATCH
            if not knn_results.empty:
                for _, row in knn_results.iterrows():
                    response.append({
                        "Type": "Recommended (CGPA Based)",
                        "University": row.get("univName", "N/A"),
                        "CGPA": row.get("cgpa", "N/A"),
                        "GRE": f"{row.get('greV','N/A')}/{row.get('greQ','N/A')}"
                    })

            # SCHOLARSHIPS
            if not sch_results.empty:
                for _, row in sch_results.iterrows():
                    response.append({
                        "Type": "Scholarship",
                        "Name": row.get("name", "N/A"),
                        "Funds": row.get("funds", "N/A"),
                        "Location": row.get("location", "N/A")
                    })

        # -------------------------------
        # ❌ FALLBACK
        # -------------------------------
        if not response:
            response = [{
                "Message": "Try: top universities in japan, cgpa 9 colleges, scholarships in usa"
            }]

        # SAVE CHAT
        session["chat_history"].append({
            "user": user_input,
            "bot": response
        })

    return render_template("chat_ai.html", chat=session["chat_history"])

# 🚪 LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)