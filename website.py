from flask import Flask, request, render_template
app = Flask(__name__)
import os
import time
import argparse, datetime, re
import cPickle as pickle
from google.cloud import language 
import json
import googleapiclient.discovery
import collections
import predict
from google.cloud import bigquery
import random
# gcloud auth activate-service-account  --key-file /Users/hemanthkondapalli/CaseRouting/emailinsight-3b9291f24d02.json
# export API_KEY=AIzaSyAY9T1IVheKFOCI9vdTp6-J77Rzk2XUiW0
# gcloud auth activate-service-account  --key-file emailinsight-3b9291f24d02.json 
# export GOOGLE_APPLICATION_CREDENTIALS=emailinsight-3b9291f24d02.json
# gcloud beta ml language analyze-entities --content="Michelangelo Caravaggio, Italian painter, is known for 'The Calling of Saint Matthew'."

GROUP_NAMES = ['technical_group', 'legal_group', 'trading_group', 'communication_group', 'energy_group', 'sales_group']
DATA_PATH = '/Users/hemanthkondapalli/CaseRouting/'
BAG_OF_WORDS_PATH = DATA_PATH + 'full_word_bags_dict.pk'



@app.route('/')
def index():
	'''
	Home page
	'''

	
		

	return render_template('home.html')
@app.route('/request')
def show_request():
	return render_template('request.html')
@app.route('/submit', methods=['POST'])
def run_pipeline():

	#retreiving results from UI
	sample_request_subject = request.form["subject"]
	sample_request_content = request.form["content"]
	sample_request_timestamp = datetime.datetime.now()

	sample_request_subject, sample_request_content = clean_text(sample_request_subject, sample_request_content)
	word_bags = unpack_word_bags(word_bags_path = BAG_OF_WORDS_PATH)
	words_groups = get_bag_of_word_counts(sample_request_subject, sample_request_content, word_bags)
	entity_count_person, entity_count_location, entity_count_organization, entity_count_event, entity_count_work_of_art, entity_count_consumer_good, sentiment_score = get_entity_counts_sentiment_score(sample_request_subject, sample_request_content)
	subject_length, subject_word_count, content_length, content_word_count, is_am, is_weekday = get_basic_quantitative_features(sample_request_subject, sample_request_content, sample_request_timestamp)

	#with open('instances.json') as f:
	#	JSON = json.load(f)
	json_to_submit = {'content_length':content_length,
					'content_word_count':content_word_count,
					'group1':words_groups[0][0],
					'group2':words_groups[1][0],
					'group3':words_groups[2][0],
					'group4':words_groups[3][0],
					'group5':words_groups[4][0],
					'group6':words_groups[5][0],
					'is_am':is_am,
					'is_weekday':is_weekday,
					'subject_length':subject_length,
					'subject_word_count':subject_word_count,
					'nlp_consumer_goods':entity_count_consumer_good,
					'nlp_events':entity_count_event,
					'nlp_locations':entity_count_location,
					'nlp_organizations':entity_count_organization,
					'nlp_persons':entity_count_person,
					'nlp_work_of_arts':entity_count_work_of_art,
					'sentiment_scores':sentiment_score
	}

	service = googleapiclient.discovery.build('ml', 'v1')
	PROJECT = 'emailinsight-1'
	MODEL = 'case_routing_model_v5'
	name = 'projects/{}/models/{}'.format(PROJECT, MODEL)
	response = service.projects().predict(
    	name=name,
    	body={'instances': [json_to_submit]}
	).execute()
	
	bigquery_client = bigquery.Client()
	dataset = bigquery_client.dataset('CaseRouting')
	table = dataset.table('Tickets')
	table.reload()

	ticket_id = ''.join(random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for i in xrange(6))
	category = str(response['predictions'][0]['classes'])
	sample_request_timestamp = sample_request_timestamp.strftime('%Y-%m-%d %H:%M:%S')
	data = [ticket_id, sample_request_subject, sample_request_content, category, sample_request_timestamp]
	rows = [data]
	erros = table.insert_data(rows)
	
	return "Thank you for your submission"


def clean_text(message_subject, message_content):
	message_subject = re.sub('[^A-Za-z0-9.?!; ]+', ' ', message_subject)
	message_content = re.sub('[^A-Za-z0-9.?!; ]+', ' ', message_content)

	return message_subject, message_content

def get_entity_counts_sentiment_score(message_subject, message_content):
	"""Extract entities using google NLP API

	Sentiment analysis inspects the given text and identifies the 
	prevailing emotional opinion within the text, especially to 
	determine a writer's attitude as positive, negative, or neutral. 

	Entity analysis inspects the given text for known entities (Proper 
	nouns such as public figures, landmarks, and so on. Common nouns 
	such as restaurant, stadium, and so on.) and returns information 
	about those entities.

	Args
	text: content of text to feed into API

	Returns:
	entity_count_person, entity_count_location, entity_count_organization, 
	entity_count_event, entity_count_work_of_art, entity_count_consumer_good,
	sentiment_score
	"""

	text = message_subject + message_content

	client = language.Client()
	document = client.document_from_text(text)


	# Detects sentiment in the document.
	annotations = document.annotate_text(include_sentiment=True,
											include_syntax=False,
											include_entities=True)

	# get overal text sentiment score
	sentiment_score = annotations.sentiment.score

	# get total counts for each entity found in text
	PERSON = []   
	LOCATION = []     
	ORGANIZATION = []      
	EVENT = []  
	WORK_OF_ART = []   
	CONSUMER_GOOD = []

	entities_found = []  
	for e in annotations.entities: 
		entities_found.append(e.entity_type)

	entity_count_person = len([i for i in entities_found if i == 'PERSON'])
	entity_count_location = len([i for i in entities_found if i == 'LOCATION'])
	entity_count_organization = len([i for i in entities_found if i == 'ORGANIZATION'])
	entity_count_event = len([i for i in entities_found if i == 'EVENT'])
	entity_count_work_of_art = len([i for i in entities_found if i == 'WORK_OF_ART'])
	entity_count_consumer_good = len([i for i in entities_found if i == 'CONSUMER_GOOD'])

	return entity_count_person, entity_count_location, entity_count_organization, entity_count_event, entity_count_work_of_art, entity_count_consumer_good, sentiment_score

def get_basic_quantitative_features(message_subject, message_content, message_time):
	""" 


	Args
	 

	Returns:

	""" 
	subject_length = len(message_subject)
	subject_word_count = len(message_subject.split())
	content_length = len(message_content)
	content_word_count = len(message_content.split())
	dt = message_time
	is_am = 'no'
	if (dt.time() < datetime.time(12)): is_am = 'yes'
	is_weekday = 'no'
	if (dt.weekday() < 6): is_weekday = 'yes'
	return subject_length, subject_word_count, content_length, content_word_count, is_am, is_weekday

def get_bag_of_word_counts(message_subject, message_content, word_bags):
 
	text = message_subject + message_content
	text = text.lower()
	# loop through all emails and count group words in each raw text
	words_groups = []
	for group_id in range(len(GROUP_NAMES)):
		work_group = []
		top_words = word_bags[GROUP_NAMES[group_id]]
		# work_group.append(len(set(top_words) & text.split()))
		work_group.append(len([w for w in text.split() if w in set(top_words)]))
		words_groups.append(work_group)
	return words_groups
 
def unpack_word_bags(word_bags_path):
	""" 

	Args:
	word_bags_path: full path and file name to pickle file holding words representing  
	each routing groups
	 

	Returns:

	"""

	with open(word_bags_path, 'rb') as handle:
		groups = pickle.load(handle)

	return groups
 
if __name__ == '__main__': 
	port = int(os.environ.get("PORT", 8000))
	app.run(debug=True, host='0.0.0.0', port=port)