#!/usr/bin/python

import pyzmail
import html2text
#import sys
#import uuid
import hashlib
import pymysql
import datetime




class Db:
	def __init__(self, conn):
		self.conn = conn
	
	
	
	@staticmethod
	def fetchAssoc(cur):
		cols = [ d[0] for d in cur.description ]
		for row in cur:
			yield dict(zip(cols, row))
	
	
	
	def insert(self, query, data = None, autoCommit = True):
		cur = self.getCursor()
		cur.execute(query, data)
		lastId = cur.lastrowid
		cur.close()
		if autoCommit:
			self.conn.commit()
		return lastId
	
	
	
	def getCursor(self):
		return self.conn.cursor()
	
	
	
	def query(self, query, data = None):
		cur = self.getCursor()
		
		cur.execute(query, data)
		cols = [ d[0] for d in cur.description ]
		for row in cur:
			yield dict(zip(cols, row))
		
		cur.close()
	
	
	
	def queryOne(self, query, data = None, softZero = True, softMany = False):
		cur = self.getCursor()
		
		cur.execute(query, data)
		if cur.rowcount == 0:
			if softZero:
				result = None
			else:
				cur.close()
				raise Exception("0 results in query '%s'" % query)
		
		elif cur.rowcount > 1:
			if softMany:
				result = None
			else:
				cur.close()
				raise Exception("More than 1 results in query '%s'" % query)
		
		else:
			cols = [ d[0] for d in cur.description ]
			result = dict(zip(cols, cur.fetchone()))
		
		cur.close()
		return result
	
	
	
	def close(self):
		self.conn.close()







def decodePart(part):
	binary = part.get_payload()
	try:
		string = binary.decode(part.charset, 'ignore')
	except LookupError:
		## Better use a detection system
		string = binary.decode('utf-8', 'ignore')
	
	return string



def handleHtml(html):
	h = html2text.HTML2Text()
	markdown = h.handle(html)
	return markdown



def handleText(markdown):
	return markdown


## The mailserver has to split it up, so one can send a mail to the feedback
## system and his grandma
def getAddress(msg, field, address = None):
	if address is not None:
		return address
		
	if len(msg.get_addresses(field)) != 1:
		raise Exception("Sorry, the mail can only be addresses %s one." % field)
	
	return msg.get_address(field)[1]

f = open("tests/format-html+text.eml", "br")

msg = pyzmail.PyzMessage.factory(f)



## Init them by command line
sender   = None
receiver = None

sender   = getAddress(msg, "from", sender)
receiver = getAddress(msg, "to",   receiver)


db = Db(pymysql.connect(
	#host        = "127.0.0.1",
	unix_socket = "/var/run/mysqld/mysqld.sock",
	user        = "CHANGEME",
	passwd      = "CHANGEME",
	db          = "CHANGEME"
))


courseData = db.queryOne("SELECT * FROM aliases a LEFT JOIN courses c ON a.course = c.id WHERE a.mail = %s", [receiver])
print(courseData)

# uuid is used to generate a random number
hashedSender = hashlib.sha256(courseData["salt"] + sender.encode())
print("From ", hashedSender.hexdigest())

## Uneindeutige ID in course data!!! (nicht klar von welcher tabelle)
binHashedSender = hashedSender.digest()
binHashedSender += b'\0' * (64 - len(binHashedSender))
senderData = db.queryOne("SELECT * FROM sender WHERE course = %s AND mailHash = %s", [courseData["course"], binHashedSender])
if senderData is not None:
	senderId = senderData["id"]
else:
	print("inserted %s" % sender)
	senderId = db.insert("INSERT INTO sender (course, mailHash) VALUES (%s, %s)", [courseData["course"], binHashedSender])

print(senderData, senderId)



if msg.html_part is not None:
	part = msg.html_part
	handler = handleHtml

elif msg.text_part is not None:
	part = msg.text_part
	handler = handleHtml

string = decodePart(part)
markdown = handler(string)
now = datetime.datetime.now()
creationDate = (now+datetime.timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
publishDate  = (now+datetime.timedelta(hours=2)).replace(minute=0,second=0,microsecond=0)

senderId = db.insert("""
	INSERT INTO messages (
		owner, 
		creationDate, 
		publishDate, 
		markdown, 
		origHtml, 
		origText, 
		publicity
	) 
	VALUES (%s, %s, %s, %s, %s, %s, %s)""",
	[
		senderId,
		creationDate.isoformat(),
		publishDate.isoformat(),
		markdown,
		None,
		None,
		"PRIVATE"
	]
)
