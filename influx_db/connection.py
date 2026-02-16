import os
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS



load_dotenv()

class InfluxDBService:
    @staticmethod
    def getClient():
        return InfluxDBClient(
            os.getenv('INFLUX_URL'),
            os.getenv('INFLUX_TOKEN'),
            os.getenv('INFLUX_ORG')
        )
    
    @staticmethod
    def getWriteApiSync(client : InfluxDBClient):
        return client.write_api(
            write_options=SYNCHRONOUS
        )

    @staticmethod
    def getQueryApi(client : InfluxDBClient):
        return client.query_api()
    
    @staticmethod
    def getOrg():
        return os.getenv('INFLUX_ORG')

    @staticmethod
    def getBucket():
        return os.getenv('INFLUX_BUCKET')
    