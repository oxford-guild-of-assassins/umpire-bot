FROM python:3
FROM gorialis/discord.py:minimal

RUN mkdir -p /usr/src/bot
WORKDIR /usr/src/bot

COPY requirements.txt ./
RUN pip install -r requirements.txt  

COPY . .

CMD [ "python3", "bot.py" ]
