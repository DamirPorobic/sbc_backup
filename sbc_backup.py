import paramiko
import time
import sys
import logging
import os 
import re

# Prepare logger 
logger = logging.getLogger('sbc_backup')
logHandler = logging.FileHandler('sbc_backup.log')
logFormatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
logHandler.setFormatter(logFormatter)
logger.addHandler(logHandler) 
logger.setLevel(logging.DEBUG)   # Set logging level of script
# logging.getLogger("paramiko").setLevel(logging.DEBUG) # Set logging level of paramiko backend

# Set key variables
hosts = ['10.100.100.10']   # List of SBCs
username = 'user'       
key = paramiko.RSAKey.from_private_key_file('I:\Keys\id_rsa.pem')
remotepath = '/code/gzConfig/dataDoc.gz'
numberOfBackups = 5    # How many backups should be keept of each device


def execute(channel, cmd):
    try: 
        cmd = cmd.strip('\n')
        channel.send(cmd + '\n' )
        
        buff=''
        while not buff.endswith('# ') and not buff.endswith('> '):
            resp = channel.recv(4096)
            buff += resp
        return buff
    except socket.timeout:
        logger.error ('Unable to send/Receive data before socket timeout.')
        
    except:
        logger.error ('Unknown error occured while trying to execute command.')
        
    return None
    
    
def cleanUpBackup(dir):
    backups = os.listdir(dir)
    if len(backups) > numberOfBackups:
        logger.info('Number of backups excised limit ' + str(len(backups)) + '/' + str(numberOfBackups) )
        backups.sort()
        logger.warning('Removing lowest revision number: ' + backups[0])
        os.remove(dir + '\\' + backups[0])
    else:
        logger.info('Number of backups within limit ' + str(len(backups)) + '/' + str(numberOfBackups))
    
    
def connectSSH(host):
    i = 1
    while True:
        logger.info('Trying to connect to ' + host + ' (' + str(i) + '/3)')
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host,username=username, pkey=key)  
            logger.info('Connected to ' + host)
            
            return ssh
        except paramiko.AuthenticationException:
            logger.error('Authentication failed when connecting to ' + host)
            return None
            
        except:
            logger.warning('Could not SSH to ' + host + ', wait and try again.')
            i += 1
            time.sleep(2)
        
        # If we could not connect within time limit
        if i == 3:
            logger.error('Could not connect to ' + host  + '. Giving up.')
            return None
    
    
def connectSFTP(host):
    try:
        transport = paramiko.Transport((host, 22))
        transport.connect(username=username, pkey=key)
        return paramiko.SFTPClient.from_transport(transport)
    except paramiko.SSHException, e:
        logger.error('Failed to open SFTP connection to ' + host)
        
    except paramiko.AuthenticationException:
        logger.error('Authentication failed when connecting to ' + host)
        
    return None
    
    
def closeConnections():
    try:
        sftp.close()
        logger.info('SFTP connection closed.')
    except:
        logger.warning('Unable to close SFTP connection, was it opened?')
        
    try:
        ssh.close()
        logger.info('SSH connection closed.')
    except:
        logger.warning('Unable to close SSH connection, was is opened?')
    

# Starting Execution here
try:
    # Start loop through list of all hosts
    for host in hosts:
        # Try to connect via SSH to host
        ssh = connectSSH(host)
         
        # Invoke interactive shell to host
        channel = ssh.invoke_shell()
         
        # If the returned connection is None, skip host and move to next
        if ssh is None:
            logger.warning('Skipping ' + host + ', moving to next host.')
            continue
          
        # Try to execute display cfg version command
        logger.info('Checking current cfg version...')
        resp = execute(channel, 'display-running-cfg-version')
        if resp is None:
            logger.warning('Executing command on ' + host + ' failed, moving to next host.')
            closeConnections()
            continue
        
        try:
            currentRev = re.search('Running configuration version is (.+?)\r\n', resp).group(1)
            logger.info('Current config revision on ' + host + ' is ' + currentRev)
        except AttributeError:
            logger.error('Unexpected response:\n' + resp)
            logger.warning('Unable to get config revision from ' + host + ', moving to next host.')
            closeConnections()
            continue
        
        # Create filename that we will use to store the backup localy
        filename = host + '-rev' + currentRev + '.gz'
        directory = host +'-backups'
        # Setup path for saving the backup localy
        localpath = os.path.dirname(os.path.realpath(__file__)) + '\\' + directory + '\\' + filename
        
        # Check if we have a directory for storing backups of this host, if not
        # create one.
        if not os.path.isdir(host +'-backups'):
            os.makedirs(host +'-backups')
        else:
            # If a backupfile with the same name exists skip creating another one
            if os.path.isfile(localpath):
                logger.warning('Backup file ' + filename + ' already exists. Moving to next host.')
                closeConnections()
                continue
                
        logger.info('Opening sftp connection and downloading file...')
            
        # Try to open SFTP connection
        sftp = connectSFTP(host)
            
        if sftp is None:
            logger.warning('Failed to open SFTP connection to ' + host  + ', moving to next host.')
            closeConnections
            continue
         
        try:
            # Try to transfer backup file via SFTP
            sftp.get(remotepath, localpath)
            logger.info('Backup transfered to ' + localpath)        
        except:
            logger.error('Failed to download dataDoc.gz, moving to next host.')
            closeConnections()
            continue
            
        cleanUpBackup(directory)
            
        # Close any open SSH and SFTP connection
        closeConnections()
    
except Exception, e:
    logger.critical(e)

except:
    logger.critical('An error occurred, unable to proceed.')
