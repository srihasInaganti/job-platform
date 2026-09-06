FROM public.ecr.aws/lambda/python:3.12
COPY handler.py requirements.txt ./
RUN pip install -r requirements.txt
CMD ["handler.handler"]