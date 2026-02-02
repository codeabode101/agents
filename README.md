# Codeabode Agents 
Use these agents to make curriculums, classwork, homework, and refine the curriculum as you learn more about your student!

In your `.env`, include a PostgreSQL database url in the `DB_URL` variable.
You will also need a Gemini API Key. Please store that in the `GEMINI_API_KEY` variable.

Please make the database and set up the backend using the [codeabode backend](https://github.com/codeabode101/webapp)

## Install 

You can use the release build provided, or:

Clone the repository
```sh
git clone https://github.com/codeabode101/agents
cd agents
```

Make a virtual environment:

```sh
python3 -m venv venv
. venv/bin/activate
```

It is **necessary** to call the folder `venv` because at the top of `codeabode.py` is:

```py
#!venv/bin/python3
```

Install all dependencies inside the venv

```sh
pip install -r requirements.txt
```

You can also use `pyinstaller` from within the venv if you want to make a contained binary. That's how the release binary was made.

## Usage

```sh
(venv) ➜  agents git:(main) ✗ ./codeabode.py                                                  
Usage: ./codeabode.py [COMMAND]

Commands:
    curriculum, c - generate a curriculum
    classwork, w - generate a classwork
    homework, hw, h - generate a homework
    refiner, refine, r - refine a curriculum
```

All commands are interactive.

First you want to create a postgresql database and provide the URL in the `.env` file. You can then run

To create your first curriculum, run the following command with no args:

```sh
./codeabode curriculum
```
