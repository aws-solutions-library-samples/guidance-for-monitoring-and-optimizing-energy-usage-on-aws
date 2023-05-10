## Guidance for Monitoring and Optimizing Energy Usage on AWS

The sample code in this project demonstrate a Reinforcement Learning based solution on optimizing energy usage on AWS. 

This RL-based solution can serve as a great starting point for optimizing energy usage for equipment with temperature and humidity sensor readings. You can further optimize this solution to fit your use case, and deploy on AWS to realize cost saving.

### RL solution workflow
![rl-high-level-demo](Image/rl-demo.png)

### Project folder structure
- `Data` - contains synthetic data for this RL demo
- `Image` - Image repo 
- `Notebooks` - contains ready to execute RL implementation in Jupyter Notebooks
- `Scripts` - contains RL implementation in .py files ready for immediate deployment

## Getting Started

The sample code is available in both python script format as well as Jupyter notebook.
Make sure you create an S3 bucket named `energy-optimization-demo-xxx` where xxx is replaced by any number 3 digit number as bucket names in Amazon S3 are unique across all existing bucket names. Within the bucket create a folder as `Model`. This is where the Reinforcement Learning model would be saved.

![S3bucket](Image/S3bucket.png)

## Using the sample

TBD

## Cleanup

TBD

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.