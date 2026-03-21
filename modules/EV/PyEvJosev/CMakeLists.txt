install(
    FILES
        ${CMAKE_CURRENT_SOURCE_DIR}/../../../lib/everest/iso15118/test/iso15118/io/pki/configs/contractLeafCert.cnf
        ${CMAKE_CURRENT_SOURCE_DIR}/../../../lib/everest/iso15118/test/iso15118/io/pki/configs/moRootCACert.cnf
        ${CMAKE_CURRENT_SOURCE_DIR}/../../../lib/everest/iso15118/test/iso15118/io/pki/configs/moSubCA1Cert.cnf
        ${CMAKE_CURRENT_SOURCE_DIR}/../../../lib/everest/iso15118/test/iso15118/io/pki/configs/moSubCA2Cert.cnf
    DESTINATION "${THIRD_PARTY_APP_DST}/josev/iso15118/shared/pki/configs"
)
