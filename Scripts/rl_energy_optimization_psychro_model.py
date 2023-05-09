#importing the libraries
import time
import csv
import json
import boto3
from datetime import datetime
import logging
import gym
import numpy as np
import pandas as pd
import psychrolib
from gym.spaces import Box
import datetime

# create logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# import the boto3 library and initiate an S3 resource
s3 = boto3.resource('s3')

#Read and standardize the data
def get_data(filepath="guidance-for-monitoring-and-optimizing-energy-usage-on-aws/Data/data.csv"):

    #Standarize the column name and format
    df = pd.read_csv(filepath) 
    print("Before", df.shape)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    print("After", df.shape)

    # Fix some inconsistencies - pyschrolib library wants humidity values 
    # represented as a decimal value between 0 and 1. A value not within those bounds will error. 
    df["return_humidity"] = df["return_humidity"] / 100
    df["outside_humidity"] = df["outside_humidity"] / 100
    df["outside_humidity"] = df["outside_humidity"].clip(0.001, 1)
    df["return_humidity"] = df["return_humidity"].clip(0.001, 1)
    df = df.dropna(axis=0, subset=["outside_humidity"])

    # Make sure we need mechanical cooling
    # TODO: Why is this being done? removing it, as it breaks the model 
    #df = df[(df.outside_temperature > 55)]
    return df

class RTU_enviroment(gym.Env):
    # psychrolib is a library for calculating thermodynamic properties of air.
    # Sets the unit system of the psychrolib library to Imperial (IP system), which is the unit system commonly used in the United States. 
    # The IP system uses units such as Fahrenheit for temperature and pounds per square inch for pressure.
    psychrolib.SetUnitSystem(psychrolib.IP)
    
    # Defines the names of the columns in the data that the environment uses.
    data_cols = [
        # "timestamp",
        "outside_enthalpy",
        "return_enthalpy",
        "outside_temperature",
        "outside_humidity",
        "outside_humidity_ratio",
        "return_temperature",
        "return_humidity",
        "return_humidity_ratio",
        "outside_humidity_grains",
        "return_humidity_grains",
    ]
    
    # Defines the names of the columns in the data that the agent can observe.
    obs_cols = [
        "outside_enthalpy",
        "return_enthalpy",
        "outside_temperature",
        "return_temperature",
    ]
    
    # Defines the names of the columns in the data that the agent can manipulate.
    action_cols = ["econ_max_enthapy", "econ_max_temperature"]
    
    # Constructor method for the environment.
    def __init__(self, env_config: dict):
        
        # Defines default values for the configuration parameters.
        config_defaults = {
            "pressure": 14.696,
            "supply_temperature": 55,
            "supply_humidity": 0.50,
            "min_econ_enthalpy_setpoint": 20.0,
            "max_econ_enthalpy_setpoint": 30.0,
            "min_econ_temp_setpoint": 40.0,
            "max_econ_temp_setpoint": 75.0,
            # From historical data which is constant, cool is enable if higher than this temp
            "cooling_enable_setpoint": 55,
            "minimum_outside_air_ratio": 0.1,
            "supply_airflow_cfm": 8000,
            "timestep": 0,
            "filepath": "guidance-for-monitoring-and-optimizing-energy-usage-on-aws/Data/data.csv",
            "min_obs": -np.inf,  # Generic value range for all obs
            "max_obs": np.inf,
            "episode_len": 200,
        }
        
        # Overrides the default values with the values passed to the constructor.
        for key, val in config_defaults.items():
            val = env_config.get(key, val)  # Override defaults with constructor parameters
            self.__dict__[key] = val  # Creates variables like self.plot_boxes, etc
            if key not in env_config:
                env_config[key] = val

        print("*********** Env Config ************")
        print("filepath", self.filepath)
        print("*********** Env End ************")

        # print only 3 decimal places
        np.set_printoptions(precision=3)
        
        # Calculates the humidity ratio and enthalpy of the supply air.
        self.supply_humidity_ratio = psychrolib.GetHumRatioFromRelHum(
            self.supply_temperature, self.supply_humidity, self.pressure
        )
        self.supply_enthalpy = psychrolib.GetMoistAirEnthalpy(
            self.supply_temperature, self.supply_humidity_ratio
        )

        # Read historical data
        self.df = get_data(self.filepath)
        
        # Calculates properties related to the outside air.
        outside_humidity_ratio = []
        outside_enthalpy = []
        for _, row in self.df.iterrows():
            humidity_ratio = psychrolib.GetHumRatioFromRelHum(
                row["outside_temperature"], row["outside_humidity"], self.pressure
            )
            outside_humidity_ratio.append(humidity_ratio)
            enthalpy = psychrolib.GetMoistAirEnthalpy(row["outside_temperature"], humidity_ratio)
            outside_enthalpy.append(enthalpy)
            
        # Adds new columns to the data.
        self.df["outside_humidity_ratio"] = outside_humidity_ratio
        self.df["outside_enthalpy"] = outside_enthalpy
        self.df["outside_humidity_grains"] = self.df["outside_humidity_ratio"] * 7000
        
        
        # Calculates properties related to the return air.
        zone_humidity_ratio = []
        zone_enthalpy = []

        for _, row in self.df.iterrows():
            humidity_ratio = psychrolib.GetHumRatioFromRelHum(
                row["return_temperature"], row["return_humidity"], self.pressure
            )
            zone_humidity_ratio.append(humidity_ratio)
            enthalpy = psychrolib.GetMoistAirEnthalpy(row["return_temperature"], humidity_ratio)
            zone_enthalpy.append(enthalpy)
            
        # Adds new columns to the data.
        self.df["return_humidity_ratio"] = zone_humidity_ratio
        self.df["return_enthalpy"] = zone_enthalpy
        self.df["return_humidity_grains"] = self.df["return_humidity_ratio"] * 7000

        # Removes rows with missing data.
        self.df = self.df[self.data_cols].dropna()

        # Action/Observation spaces
        # Defines the range of valid actions.
        self.action_space = Box(
            low=np.array([self.min_econ_enthalpy_setpoint, self.min_econ_temp_setpoint]),
            high=np.array([self.max_econ_enthalpy_setpoint, self.max_econ_temp_setpoint]),
            dtype=np.float32,
        )
        #assert self.action_space.shape[0] == len(self.action_cols)

        # TODO update min/max
        # Defines the range of valid observations.
        self.observation_space = Box(
            self.min_obs,
            self.max_obs,
            shape=(4,),
            dtype=np.float32,
        )

    # Resets the environment to the initial state.
    def reset(self):

        self.timestep = 0
        self.timestep_max = 1000

        self.recorded_data = self.df[self.obs_cols].iloc[self.timestep]

        return self.recorded_data.values


    # Computes the outside air ratio based on the current state of the system.
    def _outside_air_ratio(self):
        # Not using economizer
        if (
            self.recorded_data["outside_enthalpy"] > self.economiser_enable_max_enthalpy
            or self.recorded_data["outside_temperature"] > self.economiser_enable_max_temperature
        ):

            return self.minimum_outside_air_ratio
        # With economizer
        else:

            ratio = (self.recorded_data["return_temperature"] - self.supply_temperature) / (
                self.recorded_data["return_temperature"] - self.recorded_data["outside_temperature"]
            )

            return np.clip(ratio, self.minimum_outside_air_ratio, 1)
        
    # Advances the simulation by one time step.
    def step(self, action):

        done = False
        self.economiser_enable_max_enthalpy = action[0]
        self.economiser_enable_max_temperature = action[1]

        print("Current timestep from line 235: ", self.timestep)
        print("self.df[self.data_cols].iloc[self.timestep]: ", self.df[self.data_cols].iloc[self.timestep])
        self.recorded_data = self.df[self.data_cols].iloc[self.timestep]

        # lets calculate the worst case power requirement (min 10% outside air)
        minimum_damper_mixed_air_enthalpy = (
            self.minimum_outside_air_ratio * self.recorded_data["outside_enthalpy"]
            + (1 - self.minimum_outside_air_ratio) * self.recorded_data["return_enthalpy"]
        )

        minimum_damper_mixed_air_temp = (
            self.minimum_outside_air_ratio * self.recorded_data["outside_temperature"]
            + (1 - self.minimum_outside_air_ratio) * self.recorded_data["return_temperature"]
        )
        
        # Calculates the minimum damper power required.
        minimum_damper_power_required = (
            (minimum_damper_mixed_air_enthalpy - self.supply_enthalpy)
            * 4.5
            * self.supply_airflow_cfm
        )

        # lets use the economiser logic:
        # Calculates the power required with the economizer.
        outside_air_ratio = self._outside_air_ratio()

        # When economizer is not activated, expect to be the same as minimum damper scenario
        self.economiser_mixed_air_enthalpy = (
            outside_air_ratio * self.recorded_data["outside_enthalpy"]
            + (1 - outside_air_ratio) * self.recorded_data["return_enthalpy"]
        )
        self.economiser_mixed_air_temp = (
            outside_air_ratio * self.recorded_data["outside_temperature"]
            + (1 - outside_air_ratio) * self.recorded_data["return_temperature"]
        )

        self.economizer_power_required = (
            (self.economiser_mixed_air_enthalpy - self.supply_enthalpy)
            * 4.5
            * self.supply_airflow_cfm
        )

        # Calculates the reward.
        self.reward = -1 * self.economizer_power_required / 1000000

        # Returns the new observation, reward, and done flag.
        observations = self.df[self.obs_cols].iloc[self.timestep].values

        self.timestep += 1
        if self.timestep >= self.timestep_max:
            print("Final timestep", self.timestep)
            done = True

        return observations, self.reward, done, {}

    # def render(self, mode="human"):
    #     assert self.timestep > 0, "Please ensure env step() has been perform first..."
    #     return draw_step(self)

if __name__ == "__main__":
    config_defaults = {
        "filepath": "guidance-for-monitoring-and-optimizing-energy-usage-on-aws/Data/data.csv",
    }
    env = RTU_enviroment(env_config=config_defaults)
    obs = env.reset()
    obs, reward, done, _ = env.step([29, 75])
    print("obs", obs)
    print("reward", reward)
    #env.render()



