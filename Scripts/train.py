#importing the libraries
import boto3
import gym
from stable_baselines3 import SAC
from stable_baselines3.common.monitor import Monitor

# import the psychro model
import psychro_model as mod

# import the boto3 library and initiate an S3 client
client = boto3.client("s3")

def train():
    """
    This function will initiate the training/retraining of the model.
    It saves a SAC_RTU.zip file as an output, to then be containerized as the inference lambda. 
    
    """
    
    # create an instance of an environment using the RTU_enviroment class from model.py with the default configuration
    config_defaults = {"filepath": "../Data/data.csv", "episode_len": 1000}
    env = mod.RTU_enviroment(env_config=config_defaults)
    
    # reset the environment
    env.reset()

    #run the RTU environment with 25 and 80 as Economizer max enthalpy and Economizer max temperature respectively and return the environment observation
    state, reward, done, msg = env.step((25, 80))
    print(state.shape)
    
    # create a monitor for the environment and assign it to the same variable for convenience
    env = Monitor(env, "logs")

    # initialize an instance of the SAC algorithm using the "MlpPolicy" policy and the environment
    model = SAC("MlpPolicy", env, verbose=1)
    
    # train the model 
    #model.learn(total_timesteps=200000)
    model.learn(total_timesteps=50) #use this for testing purpose
    
    # save the trained model to a file called "SAC_RTU"
    model.save("SAC_RTU")

    # upload the saved model file to an S3 bucket named "energy1298" with a key of "model1298/SAC_RTU.zip"
    client.upload_file("SAC_RTU.zip", "energy1298", "model1298/SAC_RTU.zip")

    print("Successfully uploaded SAC_RTU.zip to S3.")

#call the "train" function to initiate the training/retraining of the model
train()
