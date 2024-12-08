from airflow import DAG # type: ignore
import requests 
import pandas as pd 
import numpy as np 
from datetime import timedelta, datetime 
from airflow.providers.http.sensors.http import HttpSensor # type: ignore
from airflow.providers.http.operators.http import SimpleHttpOperator 
from airflow.operators.python import PythonOperator 
from airflow.providers.postgres.operators.postgres import PostgresOperator 
from airflow.hooks.postgres_hook import PostgresHook

import json 
import os 

BASE_URL ="https://api.openweathermap.org/data/2.5/weather?q=" 
CITY_NAME = "Nantes"
API_KEY = os.environ.get("API_KEY")

LIST_CITIES = ["Toulouse", "Nantes","Grenoble", "Marseille", 
               "Lyon", "Montreal", "New York", "Conakry", "Dakar"]

def extract_data(list_cities): 
    datas = []
    for city in list_cities: 
        url = f"{BASE_URL}{city}&appid={API_KEY}"
        response = requests.get(url)
        datas.append(response.json())
    return datas


# Create a function to convert the temperature
def conversion_kelvin_to_celsius(temp_K): 
    temp_C = temp_K-273.15
    return temp_C


def transform_data(task_instance): 
    datas = task_instance.xcom_pull(task_ids = "Extract_weather_data")
    transformed_values = []
    for data in datas: 
        city = data["name"]
        weather_description = data["weather"][0]["description"]
        temp_c = conversion_kelvin_to_celsius(data["main"]["temp"])
        feels_like_celsius = conversion_kelvin_to_celsius(data["main"]["feels_like"])
        min_temp_c = conversion_kelvin_to_celsius(data["main"]['temp_min'])
        max_temp_c = conversion_kelvin_to_celsius(data["main"]["temp_max"])
        pressure = data["main"]["pressure"]
        humidity = data['main']["humidity"]
        wind_speed = data["wind"]["speed"]
        time_of_record = datetime.fromtimestamp(data["dt"] + data["timezone"])
        sunrise_time = datetime.fromtimestamp(data["sys"]["sunrise"] + data["timezone"])
        sunset_time = datetime.fromtimestamp(data["sys"]["sunset"] + data["timezone"])
        ## add the values in the list 
        transformed_values.append([city,
                                  weather_description, 
                                  temp_c,
                                  feels_like_celsius, 
                                  min_temp_c,
                                  max_temp_c, 
                                  pressure, 
                                  humidity, 
                                  wind_speed, 
                                  time_of_record, 
                                  sunrise_time, 
                                  sunset_time])
        COLUMNS = [ "city",
                "weather_description", 
                "temp_c",
                "feels_like_celsius", 
                "min_temp_c",
                "max_temp_c", 
                "pressure", 
                "humidity", 
                "wind_speed", 
                "time_of_record", 
                "sunrise_time", 
                "sunset_time"
        ]
        
        ## Create a dataframe 
        dataset = pd.DataFrame(transformed_values, columns=COLUMNS)
        
        # Create a dataframe 
        transformed_data = pd.DataFrame(columns=COLUMNS)
        ## Concatenate the data 
        transformed_data = pd.concat([transformed_data, dataset])
    ## Return the datas
    return  transformed_data

## Create function for to insert the data in database 
def insert_book_data_into_postgre(task_instance): 
    transformed_data = task_instance.xcom_pull(task_ids = "Transform_weather_data")
    print(transformed_data)
    postgres_hook = PostgresHook(postgres_conn_id = "weather_database_connection")
    connection = postgres_hook.get_conn()
    cursor = connection.cursor()
    ## Create a sql query for to insert data 
    insert_query = """
            INSERT INTO Weather_table (
                            "city",
                            "weather_description", 
                            "temp_c",
                            "feels_like_celsius", 
                            "min_temp_c",
                            "max_temp_c", 
                            "pressure", 
                            "humidity", 
                            "wind_speed", 
                            "time_of_record", 
                            "sunrise_time", 
                            "sunset_time")

                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s, %s)


    """
    # Convert each row to a tuple using apply()
    tuples = transformed_data.apply(lambda row: tuple(row), axis=1)
    print(tuples)
    for record in tuples: 
         cursor.execute(insert_query,record)
         
    connection.commit()
    cursor.close()
    connection.close()
       
default_args = {
            "owner": "airflow", 
            "depends_on_past" :False, 
            "start_date" : datetime(2024,12,6),
            "email" :["thiernosidybah232@gmail.com"], 
            "email_on_failure" : False, 
            "email_on_retry" : False, 
            "retries": 2, 
            "retry_delay" :timedelta(minutes=1)
}

# Create the DAG

with DAG( "weather_dag", 
         default_args = default_args, 
         schedule_interval = "@daily", 
         catchup = False) as dag : 

        is_weather_api_ready = HttpSensor(
                        task_id = "Is_weather_api_ready", 
                        http_conn_id = "weathermap_api", 
                        endpoint = "/data/2.5/weather?q=Nantes&appid=92a2228961d1701676a43daabb355f4d"
        )
        extract_weather_data = PythonOperator(
                        task_id = 'Extract_weather_data', 
                        python_callable = extract_data, 
                        op_args = [LIST_CITIES]
        )

        
        Transform_data = PythonOperator(
                        task_id = "Transform_weather_data", 
                        python_callable = transform_data
        )
    
        create_table_task = PostgresOperator(
                task_id = "create_table", 
                postgres_conn_id = "weather_database_connection", 
                sql = """
                        CREATE TABLE IF NOT EXISTS Weather_table(
                            city TEXT,
                            weather_description TEXT , 
                            temp_c NUMERIC,
                            feels_like_celsius NUMERIC, 
                            min_temp_c NUMERIC,
                            max_temp_c NUMERIC, 
                            pressure NUMERIC, 
                            humidity NUMERIC, 
                            wind_speed NUMERIC, 
                            time_of_record TIMESTAMP, 
                            sunrise_time TIMESTAMP, 
                            sunset_time TIMESTAMP ); 
                    """
        )
        insert_weather_data_trask = PythonOperator(
                task_id = "insert_book_data", 
                python_callable = insert_book_data_into_postgre
        )

        is_weather_api_ready >> extract_weather_data >>  Transform_data >> create_table_task >> insert_weather_data_trask

