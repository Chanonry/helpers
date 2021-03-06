"""
module to contain all logic for aws s3 file handling

"""

from botocore.exceptions import ClientError
import os


def bucket_access(bucket, s3, logger):
    """
    test accessibility of an s3 bucket

    :param bucket:
    :param s3: s3 client object
    :param logger: logging object
    :return: access : bool: can access the bucket
    """
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        logger.critical("bucket {b} is inaccessible.".format(b=bucket))
        access = False
    else:
        logger.debug(" bucket {b} is accessible".format(b=bucket))
        access = True
    return access


def key_access(bucket, key, s3, logger):
    """
    test accessibility of file key in a bucket

    :param bucket:
    :param key:
    :param s3: s3 client
    :param logger: logging object
    :return: access : bool: can access the key
    """
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except ClientError:
        logger.critical("key {f} does not exist or is inaccessible.".format(f=key))
        access = False
    else:
        logger.debug(" key {f} is accessible".format(f=key))
        access = True

    return access


def download(bucket, s3_file, local_file, s3, logger):
    """
    download a file from an s3 bucket to local storage

    :param bucket: source bucket for the file
    :param s3_file: file
    :param local_file: path to save s3_file locally
    :param s3: the configured s3 client
    :param logger: the configured logger object
    :return: success : bool: operation successful
    """
    # test s3 resources are accessible
    source_flag = bucket_access(bucket=bucket, s3=s3, logger=logger)
    key_flag = key_access(bucket=bucket, key=s3_file, s3=s3, logger=logger)

    if source_flag and key_flag:
        logger.debug("downloading {f}".format(f=s3_file))
        try:
            s3.download_file(Bucket=bucket, Key=s3_file, Filename=local_file)
        except ClientError as e:
            success = False
            if e.response['ResponseMetadata']['HTTPStatusCode'] == 404:
                logger.critical("s3 object not found during file download")
            else:
                logger.critical("Unexpected error during download: %s" % e)
        else:
            logger.debug("download of {f} succeeded".format(f=s3_file))
            success = True

        if os.path.isfile(local_file) is False:
            logger.critical("{f} download possible but not saved locally".format(f=s3_file))
            success = False
    else:
        logger.error(
            "{f} download from {b} ABORTED - inaccessible s3 resource".format(f=s3_file, b=bucket))
        success = False

    return success


def upload(bucket, s3_key, local_file, s3, logger):
    """
    uploads a file from local to s3 bucket and retries on errors

    :param bucket: target bucket
    :param s3_key: s3 file key
    :param local_file: local file to upload /tmp
    :param s3: s3 client object
    :param logger: logger object
    :return: success : bool: operation successful
    """

    try:
        s3.upload_file(Filename=local_file, Bucket=bucket, Key=s3_key)
    except ClientError as e:
        success = False
        if e.response['ResponseMetadata']['HTTPStatusCode'] == 404:
            logger.critical("Bucket not found {b}".format(b=bucket))
        else:
            logger.critical("Unexpected error: %s" % e)
    except OSError:
        success = False
        logger.critical("local file error on upload to pdf-fixed")
    else:
        success = True
    return success


def move(source_bucket, target_bucket, source_file, target_file, local_file, s3_client, logger):
    """
    abstracted logic for managed move of a file from one bucket to another

    :param source_bucket: bucket containing the original file
    :param target_bucket: move the file into this bucket
    :param source_file: source file name
    :param target_file: target file name
    :param local_file: locally saved copy of the source file
    :param s3_client:
    :param logger:
    :return: abort : boolean flag: if this fails then abort the function
    """

    source_flag = bucket_access(bucket=source_bucket, s3=s3_client, logger=logger)
    key_flag = key_access(bucket=source_bucket, key=source_file, s3=s3_client, logger=logger)
    target_flag = bucket_access(bucket=target_bucket, s3=s3_client, logger=logger)

    if source_flag and key_flag and target_flag:
        move_success = move_core(source_bucket=source_bucket,
                                 target_bucket=target_bucket,
                                 source_file=source_file,
                                 target_file=target_file,
                                 local_file=local_file,
                                 s3_client=s3_client,
                                 logger=logger)
        if not move_success:
            abort = True
            logger.error("{f} move to {b} FAILED".format(f=source_file, b=target_bucket))
        else:
            logger.info("{f} moved to {b}".format(f=source_file, b=target_bucket))
            abort = False
    else:
        logger.error(
            "{f} move to {b} ABORTED due to inaccessible s3 resource".format(f=source_file, b=target_bucket))
        abort = True

    return abort


def move_core(source_bucket, target_bucket, source_file, target_file, local_file, s3_client, logger):
    """
    lowest level code - 'moves' a local file to one s3 bucket and deletes the original after
    checking the upload is successful

    :param source_bucket:
    :param target_bucket:
    :param source_file: file key
    :param target_file: file key
    :param local_file:
    :param s3_client: s3 client object
    :param logger: logger object
    :return: move_success : bool: operation successful
    """

    delete_flag = False

    upload_flag = upload(bucket=target_bucket,
                         s3_key=target_file,
                         local_file=local_file,
                         s3=s3_client,
                         logger=logger)

    key_flag = key_access(bucket=target_bucket, key=target_file, s3=s3_client, logger=logger)

    if upload_flag and key_flag:
        logger.debug("upload success")
        # delete the original file from the Stack Bucket
        try:
            s3_client.delete_object(Bucket=source_bucket, Key=source_file)
        except ClientError as e:
            delete_flag = False
            if e.response['ResponseMetadata']['HTTPStatusCode'] == 404:
                logger.error("{s} file not found - delete from {b} failed".format(s=source_file, b=source_bucket))
                logger.error(e)
            else:
                logger.error("{s} delete from {b} failed".format(s=source_file, b=source_bucket))
                logger.error(e)
        else:
            delete_flag = True

    if upload_flag and key_flag and delete_flag:
        move_success = True
    else:
        move_success = False

    return move_success
