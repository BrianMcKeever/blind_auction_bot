import sqlite3

connection = sqlite3.connect("user.db")
cursor = connection.cursor()
cursor.execute("create table if not exists user (name text unique, rank text, discord_name text)")
connection.commit()

f = open('roster.txt', 'r')
for line in f:
    values = line.split("\t")
    name = values[0].strip()
    rank = values[3].strip()
    print(name, rank)

    connection.execute('insert into user values (?, ?, ?)', (name, rank, None))

connection.commit()
connection.close()
