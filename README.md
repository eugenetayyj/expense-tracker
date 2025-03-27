# Local Testing (Web hook)
2. Run the venv with `source venv/bin/activate`
3. Run the appliation with `uvicorn api:app --reload --port 8000`
4. run `ngrok http 8000`
5. Use ngrok to create a tunnel to your local machine
6. Set the telegram webhook to: {ngrok url}/webhook
7. Test

# Local Testing (Polling)
2. Run the venv with `source venv/bin/activate`
3. Run the application with `python main.py` (note that this will delete current webhook)
4. Test
