# configuration file, contains the essential info for instances and load balancer
import os

image_id = 'ami-056cedfc3a39746c6'
key_pair = 'ece1779'
security_group = 'launch-wizard-1'
user_data = '''Content-Type: multipart/mixed; boundary="//"
MIME-Version: 1.0

--//
Content-Type: text/cloud-config; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Content-Disposition: attachment; filename="cloud-config.txt"

#cloud-config
cloud_final_modules:
- [scripts-user, always]

--//
Content-Type: text/x-shellscript; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Content-Disposition: attachment; filename="userdata.txt"

#!/bin/bash
cd /home/ubuntu/Desktop
./start.sh
--//'''
elb_arn = 'arn:aws:elasticloadbalancing:us-east-1:767240586870:loadbalancer/app/loadbalancer/3a7654beb0b62d6f'
elb_dns = 'loadbalancer-499649262.us-east-1.elb.amazonaws.com'
elb_name = 'loadbalancer'
target_group_arn = 'arn:aws:elasticloadbalancing:us-east-1:767240586870:targetgroup/targetgroup/4c19b0955a84dd51'
target_group_dimension = 'targetgroup/targetgroup/4c19b0955a84dd51'
ELB_dimension = 'app/loadbalancer/3a7654beb0b62d6f'
iam_arn = 'arn:aws:iam::767240586870:instance-profile/S3FullAccess'
placement_group = 'usergroup'  # placement group for workers
manager_group = 'managergroup'  # placement group for managers

# INSTANCE_ID = 'i-027a3b0141ec3303f'
# ZONE = 'us-east-1f'
BUCKET_NAME = 'ece1779-a2-s3-images'

class Config(object):
    SECRET_KEY = 'ECE1779'
    SQLALCHEMY_DATABASE_URI = 'mysql+mysqlconnector://root:19971014Zbwl@database-1.cjap7jvaq7b8.us-east-1.rds.amazonaws.com/ece1779a2'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


