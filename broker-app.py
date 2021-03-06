#!/usr/bin/env python
"""
desc goes here 
"""
__author__ = "jupp"
__license__ = "Apache 2.0"

from flask import Flask, Markup, flash, request, render_template, redirect, url_for
from broker.hcaxlsbroker import SpreadsheetSubmission
from broker.ingestapi import IngestApi
from broker.stagingapi import StagingApi
from werkzeug.utils import secure_filename
import os, sys
import tempfile
import threading
import logging

STATUS_LABEL = {
    'Valid': 'label-success',
    'Validating': 'label-info',
    'Invalid': 'label-danger',
    'Submitted': 'label-default',
    'Complete': 'label-default'
}

DEFAULT_STATUS_LABEL = 'label-warning'


HTML_HELPER = {
    'status_label': STATUS_LABEL,
    'default_status_label': DEFAULT_STATUS_LABEL
}


app = Flask(__name__, static_folder='static')
app.secret_key = 'cells'

@app.route('/')
def index():
    submissions = []
    try:
        submissions = IngestApi().getSubmissions()
    except Exception as e:
        flash("Can't connect to ingest API!!", "alert-danger")
    return render_template('index.html', submissions=submissions, helper=HTML_HELPER)

@app.route('/submissions/<id>')
def get_submission_view(id):
    ingest_api = IngestApi()
    submission = ingest_api.getSubmissionIfModifiedSince(id, None)

    if(submission):
        response = ingest_api.getProjects(id)

        projects = []

        if('_embedded' in response and 'projects' in response['_embedded']):
            projects = response['_embedded']['projects']

        project = projects[0] if projects else None # there should always 1 project

        files = []

        response = ingest_api.getFiles(id)
        if('_embedded' in response and 'files' in response['_embedded']):
            files = response['_embedded']['files']

        filePage = None
        if('page' in response):
            filePage = response['page']
            filePage['len'] = len(files)

        bundleManifests = []
        bundleManifestObj = {}

        response = ingest_api.getBundleManifests(id)
        if('_embedded' in response and 'bundleManifests' in response['_embedded']):
            bundleManifests = response['_embedded']['bundleManifests']

        bundleManifestObj['list'] = bundleManifests
        bundleManifestObj['page'] = None

        if('page' in response):
            bundleManifestObj['page'] = response['page']
            bundleManifestObj['page']['len'] = len(bundleManifests)

        return render_template('submission.html',
                               sub=submission,
                               helper=HTML_HELPER,
                               project=project,
                               files=files,
                               filePage=filePage,
                               bundleManifestObj=bundleManifestObj)
    else:
        flash("Submission doesn't exist!", "alert-danger")
        return  redirect(url_for('index'))

@app.route('/submissions/<id>/files')
def get_submission_files(id):
    ingest_api = IngestApi()
    response = ingest_api.getFiles(id)

    files = []
    if('_embedded' in response and 'files' in response['_embedded']):
        files = response['_embedded']['files']

    filePage = None
    if('page' in response):
        filePage = response['page']
        filePage['len'] = len(files)


    return render_template('submission-files-table.html',
                           files=files,
                           filePage=filePage,
                           helper=HTML_HELPER)

@app.route('/upload', methods=['POST'])
def upload_file():
    if request.method == 'POST':
        print ("saving..")
        f = request.files['file']
        filename = secure_filename(f .filename)
        path = os.path.join(tempfile.gettempdir(), filename)
        f.save(path)

        # do a dry run to minimally validate spreadsheet
        submission = SpreadsheetSubmission(dry=True)
        try:
            submission.submit(path,None)
        except ValueError as e:
            flash(str(e), 'alert-danger')
            return redirect(url_for('index'))
        except Exception as e:
            flash(str(e), 'alert-danger')
            return redirect(url_for('index'))

        # if we get here can go ahead and submit
        submission.dryrun = False
        submissionUrl = submission.createSubmission()
        thread = threading.Thread(target=submission.submit, args=(path,submissionUrl))
        thread.start()

        ingestApi = IngestApi()
        submissionUUID = ingestApi.getObjectUuid(submissionUrl)
        displayId= submissionUUID or '<UUID not generated yet>'
        submissionId = submissionUrl.rsplit('/', 1)[-1]

        message = Markup("Submission created with UUID : <a class='submission-id' href='"+submissionUrl+"'>"+ displayId +"</a>")

        flash(message, "alert-success")
        return redirect(url_for('index') + '#' + submissionId) # temporarily adding submission id in url for integration testing
    flash("You can only POST to the upload endpoint", "alert-warning")
    return  redirect(url_for('index'))

@app.route('/submit', methods=['POST'])
def submit_envelope():
    subUrl = request.form.get("submissionUrl")
    ingestApi = IngestApi()
    if subUrl:
        text = ingestApi.finishSubmission(subUrl)

    return  redirect(url_for('index'))

@app.route('/staging/delete', methods=['POST'])
def delete_staging():
    subUrl = request.form.get("submissionUrl")
    submissionId = subUrl.rsplit('/', 1)[-1]
    if submissionId:
        ingestApi = IngestApi()
        uuid = ingestApi.getObjectUuid(subUrl)
        stagingApi = StagingApi()
        text = stagingApi.deleteStagingArea(uuid)
        message = Markup("Staging area deleted for <a href='" + text + "'>" + text + "</a>")
        flash(message, "alert-success")
    return      redirect(url_for('index'))

if __name__ == '__main__':

    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    app.run(host='0.0.0.0', port=5000)
