class Config:
    # AWS Information
    ec2_region = "eu-west-2" # London  # Same as environment variable EC2_REGION
    ec2_amis = ['ami-09c4a4b013e66b291']
    ec2_keypair = 'OnDemandMinecraft'
    ec2_secgroups = ['sg-0441198b7b0617d3a']
    ec2_instancetype = 't3.small'
